#!/usr/bin/env python
import cv2
import math
import os
import sympy
import sys
import time
import PIL
import yaml
import numpy as np

import matplotlib

import mxnet
from mxnet import gpu
from mxnet import nd

from yolo_modules import yolo_cv
from yolo_modules import yolo_gluon
from yolo_modules import global_variable


class LPGenerator():
    def __init__(self, img_h, img_w, class_index=1):
        self.class_index = int(class_index)
        self.h = img_h
        self.w = img_w
        self.LP_WH = [[380, 160], [320, 150], [320, 150]]
        self.x = [np.array([7, 56, 106, 158, 175, 225, 274, 324]),
                  np.array([7, 57, 109, 130, 177, 223, 269])]

        self.font0 = [None] * 35
        self.font1 = [None] * 35

        module_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(module_dir, 'fonts')

        self.dot = PIL.Image.open(fonts_dir+"/34.png")
        self.dot = self.dot.resize((10, 70), PIL.Image.BILINEAR)

        for font_name in range(0, 34):
            f = PIL.Image.open(fonts_dir+'/'+str(font_name)+".png")
            self.font0[font_name] = f.resize((45, 90), PIL.Image.BILINEAR)
            self.font1[font_name] = f.resize((40, 80), PIL.Image.BILINEAR)

        self.project_rect_6d = ProjectRectangle6D(*self.LP_WH[0])

        self.pil_image_enhance = yolo_cv.PILImageEnhance(
            M=0., N=0., R=0., G=1.0, noise_var=10.)

        self.augs = mxnet.image.CreateAugmenter(
            data_shape=(3, self.h, self.w),
            inter_method=10, pca_noise=1.0,
            brightness=0.5, contrast=0.5, saturation=0.3, hue=1.0)

        self.augs2 = mxnet.image.CreateAugmenter(
            data_shape=(3, self.h, self.w),
            inter_method=10, pca_noise=0.1,
            brightness=0.7, contrast=0.7, saturation=0.7, hue=1.0)

    def draw_LP(self):
        LP_type = 0  # np.random.randint(2)
        LP_w, LP_h = self.LP_WH[LP_type]
        x = self.x[LP_type]
        label = []
        if LP_type == 0:  # ABC-1234
            LP = PIL.Image.new('RGBA', (LP_w, LP_h), yolo_cv._color[6])
            abc = np.random.randint(10, 34, size=3)
            for i, j in enumerate(abc):
                LP.paste(self.font0[j], (x[i], 35))
                label.append([j, float(x[i])/LP_w, float(x[i]+45)/LP_w])

            LP.paste(self.dot, (x[3], 45))

            num = np.random.randint(0, 9, size=4)
            num = [9 if i == 4 else i for i in num]  # exclude four

            for i, j in enumerate(num):
                LP.paste(self.font0[j], (x[i+4], 35))
                label.append([j, float(x[i+4])/LP_w, float(x[i+4]+45)/LP_w])
        '''
        if LP_type == 1:  # AB-1234
            LP = PIL.Image.new('RGBA', (LP_w, LP_h), yolo_cv._color[7])
            abc = np.random.randint(10, 34, size=2)
            for i, j in enumerate(abc):
                LP.paste(self.font1[j], (x[i], 40))
                label.append([j, float(x[i])/LP_w, float(x[i]+40)/LP_w])

            LP.paste(self.dot, (x[2], 45))

            num = np.random.randint(0, 10, size=4)
            for i, j in enumerate(num):
                LP.paste(self.font1[j], (x[i+3], 40))
                label.append([j, float(x[i+3])/LP_w, float(x[i+3]+40)/LP_w])
        '''
        return LP, LP_type, label

    def random_projection_LP_6D(self, LP, in_size, out_size, r_max):
        Z = np.random.uniform(low=1500., high=5000.)
        X = (Z * 9 / 30.) * np.random.uniform(low=-1, high=1)
        Y = (Z * 7 / 30.) * np.random.uniform(low=-1, high=1)
        r1 = np.random.uniform(low=-1, high=1) * r_max[0] * math.pi / 180.
        r2 = np.random.uniform(low=-1, high=1) * r_max[1] * math.pi / 180.
        r3 = np.random.uniform(low=-1, high=1) * r_max[2] * math.pi / 180.

        pose_6d = [X, Y, Z, r1, r2, r3]
        projected_points = self.project_rect_6d(pose_6d)

        M = cv2.getPerspectiveTransform(
            projected_points,
            np.float32([[380, 160], [0, 160], [0, 0], [380, 0]]))

        LP = LP.transform(
            in_size[::-1],
            PIL.Image.PERSPECTIVE,
            M.reshape(-1),
            PIL.Image.BILINEAR)

        LP = LP.resize((out_size[1], out_size[0]), PIL.Image.BILINEAR)
        LP, _ = self.pil_image_enhance(LP, G=1.0, noise_var=5.0)

        mask = yolo_gluon.pil_mask_2_rgb_ndarray(LP.split()[-1])
        image = yolo_gluon.pil_rgb_2_rgb_ndarray(LP, augs=self.augs2)

        x = X * self.project_rect_6d.fx / Z + self.project_rect_6d.cx
        x = x * out_size[1] / float(self.project_rect_6d.camera_w)

        y = Y * self.project_rect_6d.fy / Z + self.project_rect_6d.cy
        y = y * out_size[0] / float(self.project_rect_6d.camera_h)

        label = nd.array([[1] + [X, Y, Z, r1, r2, r3, x, y]])

        return mask, image, label

    def add(self, bg_batch, r_max, add_rate=1.0):
        ctx = bg_batch.context
        bs = bg_batch.shape[0]
        h = bg_batch.shape[2]
        w = bg_batch.shape[3]

        mask_batch = nd.zeros_like(bg_batch)
        image_batch = nd.zeros_like(bg_batch)
        label_batch = nd.ones((bs, 1, 10), ctx=ctx) * (-1)

        for i in range(bs):
            if np.random.rand() > add_rate:
                continue

            LP, LP_type, _ = self.draw_LP()

            output_size = (h, w)
            input_size = (
                self.project_rect_6d.camera_h,
                self.project_rect_6d.camera_w)

            mask, image, label = self.random_projection_LP_6D(
                LP, input_size, output_size, r_max)

            mask_batch[i] = mask.as_in_context(ctx)
            image_batch[i] = image.as_in_context(ctx)
            label_batch[i, :, :-1] = label
            label_batch[i, :, -1] = LP_type

        img_batch = bg_batch * (1 - mask_batch) + image_batch * mask_batch
        img_batch = nd.clip(img_batch, 0, 1)

        return img_batch, label_batch

    def render(self, bg_batch):
        ctx = bg_batch.context
        bs = bg_batch.shape[0]
        h = bg_batch.shape[2]
        w = bg_batch.shape[3]

        mask_batch = nd.zeros_like(bg_batch)
        image_batch = nd.zeros_like(bg_batch)
        label_batch = nd.ones((bs, 7, 3), ctx=ctx) * (-1)

        for i in range(bs):
            LP, LP_type, labels = self.draw_LP()
            # LP_w, LP_h = LP.size
            resize = np.random.uniform(low=0.9, high=1.0)
            LP_w = LP.size[0] * resize
            LP_h = LP.size[1] * resize * np.random.uniform(low=0.9, high=1.1)

            LP_w = int(LP_w)
            LP_h = int(LP_h)
            LP = LP.resize((LP_w, LP_h), PIL.Image.BILINEAR)

            LP, r = self.pil_image_enhance(LP, M=10.0, N=10.0, R=5.0, G=8.0)

            paste_x = np.random.randint(int(-0.1*LP_w), int(self.w-0.9*LP_w))
            paste_y = np.random.randint(int(-0.1*LP_h), int(self.h-0.9*LP_h))

            tmp = PIL.Image.new('RGBA', (self.w, self.h))
            tmp.paste(LP, (paste_x, paste_y))

            mask = yolo_gluon.pil_mask_2_rgb_ndarray(tmp.split()[-1])
            image = yolo_gluon.pil_rgb_2_rgb_ndarray(tmp, augs=self.augs)

            mask_batch[i] = mask.as_in_context(ctx)
            image_batch[i] = image.as_in_context(ctx)

            r = r * np.pi / 180
            offset = paste_x + abs(LP_h*math.sin(r)/2)
            # print(labels)
            for j, c in enumerate(labels):
                label_batch[i, j, 0] = c[0]
                label_batch[i, j, 1] = (offset + c[1]*LP_w*math.cos(r))/self.w
                label_batch[i, j, 2] = (offset + c[2]*LP_w*math.cos(r))/self.w

        img_batch = bg_batch*(1 - mask_batch)/255. + image_batch * mask_batch
        img_batch = nd.clip(img_batch, 0, 1)

        return img_batch, label_batch

    def test_render(self, n):
        LP, LP_type, labels = self.draw_LP()
        # LP_w, LP_h = LP.size
        LP_w = LP.size[0]
        LP_h = LP.size[1]
        LP.show()
        '''
        plt.ion()
        fig = plt.figure()
        ax = []
        for i in range(n):
            ax.append(fig.add_subplot(321+i))
        while True:
            img_batch, label_batch = self.render(n)
            for i in range(n):
                label = label_batch[i]
                s = self.label2nparray(label)
                ax[i].clear()
                ax[i].plot(range(8, 384, 16), (1-s)*160, 'r-')
                ax[i].imshow(img_batch[i].transpose((1, 2, 0)).asnumpy())

            raw_input('next')
        '''
    def label2nparray(self, label):
        score = nd.zeros((24))
        for L in label:  # all object in the image
            if L[0] < 0:
                continue
            text_cent = ((L[3] + L[1])/2.)
            left = int(round((text_cent.asnumpy()[0]-15./self.w)*24))
            right = int(round((text_cent.asnumpy()[0]+15./self.w)*24))
            #left = int(round(L[1].asnumpy()[0]*24))
            #right = int(round(L[3].asnumpy()[0]*24))
            for ii in range(left, right):
                box_cent = (ii + 0.5) / 24.
                score[ii] = 1-nd.abs(box_cent-text_cent)/(L[3]-L[1])
        return score.asnumpy()

    def test_add(self, b):
        batch_iter = load(b, h, w)
        for batch in batch_iter:
            imgs = batch.data[0].as_in_context(ctx[0])  # b*RGB*w*h
            labels = batch.label[0].as_in_context(ctx[0])  # b*L*5
            #imgs = nd.zeros((b, 3, self.h, self.w), ctx=gpu(0))*0.5
            tic = time.time()
            imgs, labels = self.add(imgs/255, labels)
            #print(time.time()-tic)
            for i, img in enumerate(imgs):
                R, G, B = img.transpose((1, 2, 0)).split(num_outputs=3, axis=-1)
                img = nd.concat(B, G, R, dim=-1).asnumpy()
                print(labels[i])
                cv2.imshow('%d' % i, img)
            if cv2.waitKey(0) & 0xFF == ord('q'):
                break


class ProjectRectangle6D():
    def __init__(self, w, h):
        h /= 2.
        w /= 2.
        path = global_variable.camera_parameter_path
        with open(path) as f:
            spec = yaml.load(f)

        self.camera_w = spec['image_width']
        self.camera_h = spec['image_height']
        self.fx = spec['projection_matrix']['data'][0]
        self.fy = spec['projection_matrix']['data'][5]
        self.cx = spec['projection_matrix']['data'][2]
        self.cy = spec['projection_matrix']['data'][6]
        '''
        self.camera_w = sympy.Symbol('w')
        self.camera_h = sympy.Symbol('h')
        self.fx = sympy.Symbol('fx')
        self.fy = sympy.Symbol('fy')
        self.cx = sympy.Symbol('cx')
        self.cy = sympy.Symbol('cy')

        self.X = sympy.Symbol('X')
        self.Y = sympy.Symbol('Y')
        self.Z = sympy.Symbol('Z')
        self.r1 = sympy.Symbol('r1')
        self.r2 = sympy.Symbol('r2')
        self.r3 = sympy.Symbol('r3')

        P_3d = sympy.Matrix(
            [[w, -w, -w, w],
             [h, h, -h, -h],
             [0, 0, 0, 0]])

        R1 = sympy.Matrix(
            [[1, 0, 0],
             [0, sympy.cos(self.r1), -sympy.sin(self.r1)],
             [0, sympy.sin(self.r1), sympy.cos(self.r1)]])

        R2 = sympy.Matrix(
            [[sympy.cos(self.r2), 0, sympy.sin(self.r2)],
             [0, 1, 0],
             [-sympy.sin(self.r2), 0, sympy.cos(self.r2)]])

        R3 = sympy.Matrix(
            [[sympy.cos(self.r3), -sympy.sin(self.r3), 0],
             [sympy.sin(self.r3), sympy.cos(self.r3), 0],
             [0, 0, 1]])

        T_matrix = sympy.Matrix(
            [[self.X]*4,
             [self.Y]*4,
             [self.Z]*4])

        intrinsic_matrix = sympy.Matrix(
            [[self.fx, 0, self.cx],
             [0, self.fy, self.cy],
             [0, 0, 1]])

        extrinsic_matrix = R3 * R2 * R1 * P_3d + T_matrix
        self.projection_matrix = intrinsic_matrix * extrinsic_matrix
        '''

    def __call__(self, pose_6d):
        # [mm, mm, mm, rad, rad, rad]
        points = np.zeros((4, 2))
        '''
        subs = {
            self.X: pose_6d[0], self.Y: pose_6d[1], self.Z: pose_6d[2],
            self.r1: pose_6d[3], self.r2: pose_6d[4], self.r3: pose_6d[5]}
        ans = self.projection_matrix.evalf(subs=subs)
        '''
        ans = self.projection_matrix(pose_6d[:6])
        for i in range(4):
            points[i, 0] = ans[0, i] / ans[2, i]
            points[i, 1] = ans[1, i] / ans[2, i]

        return points.astype(np.float32)

    def projection_matrix(self, pose):
        X, Y, Z, r1, r2, r3 = pose
        sin = math.sin
        cos = math.cos

        a = sin(r1) * cos(r2) * 84.0
        b = sin(r1) * sin(r2) * cos(r3) * 84.0
        c = sin(r2) * 199.5
        d = sin(r3) * cos(r1) * 84.0
        e = cos(r2) * cos(r3) * 199.5
        f = sin(r1) * sin(r2) * sin(r3) * 84.0
        g = sin(r3) * cos(r2) * 199.5
        h = cos(r1) * cos(r3) * 84.0

        ans = np.array([
            [self.cx*(Z + a - c) + self.fx*(X + b - d + e),
             self.cx*(Z + a + c) + self.fx*(X + b - d - e),
             self.cx*(Z - a + c) + self.fx*(X - b + d - e),
             self.cx*(Z - a - c) + self.fx*(X - b + d + e)],
            [self.cy*(Z + a - c) + self.fy*(Y + f + g + h),
             self.cy*(Z + a + c) + self.fy*(Y + f - g + h),
             self.cy*(Z - a + c) + self.fy*(Y - f - g - h),
             self.cy*(Z - a - c) + self.fy*(Y - f + g - h)],
            [Z + a - c, Z + a + c, Z - a + c, Z - a - c]])

        return ans

    def add_edges(self, img, pose, LP_size=(160, 380)):
        corner_pts = self.__call__(pose)

        x_scale = img.shape[1] / float(self.camera_w)
        y_scale = img.shape[0] / float(self.camera_h)

        corner_pts[:, 0] = corner_pts[:, 0] * x_scale
        corner_pts[:, 1] = corner_pts[:, 1] * y_scale
        # 2----------->3
        # ^            |
        # |  ABC-1234  |
        # |            |
        # 1<-----------0
        LP_corner = np.float32([[LP_size[1], LP_size[0]],
                                [0, LP_size[0]],
                                [0, 0],
                                [LP_size[1], 0]])

        M = cv2.getPerspectiveTransform(corner_pts, LP_corner)
        clipped_LP = cv2.warpPerspective(img, M, (LP_size[1], LP_size[0]))
        p = np.expand_dims(corner_pts, axis=0).astype(np.int32)
        img = cv2.polylines(img, p, 1, (0, 0, 255), 2)

        return img, clipped_LP


if __name__ == '__main__':
    g = LPGenerator(640, 480, 0)
    g.test_render(4)
'''
a = 84.0*sin(r1)*cos(r2)
b = 84.0*sin(r1)*sin(r2)*cos(r3)
c = 199.5*sin(r2)
d = 84.0*sin(r3)*cos(r1)
e = 199.5*cos(r2)*cos(r3)
f = 84.0*sin(r1)*sin(r2)*sin(r3)
g = 199.5*sin(r3)*cos(r2)
h = 84.0*cos(r1)*cos(r3)

[
 [
  cx*(Z + a - c) + fx*(X + b - d + e),
  cx*(Z + a + c) + fx*(X + b - d - e),
  cx*(Z - a + c) + fx*(X - b + d - e),
  cx*(Z - a - c) + fx*(X - b + d + e)],

 [
  cy*(Z + a - c) + fy*(Y + f + g + h),
  cy*(Z + a + c) + fy*(Y + f - g + h),
  cy*(Z - a + c) + fy*(Y - f - g - h),
  cy*(Z - a - c) + fy*(Y - f + g - h)],

 [
  Z + a - c,
  Z + a + c,
  Z - a + c,
  Z - a - c]
]
'''
