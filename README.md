# Lincese Plate & OCR
## Dependency: cuda10, ROS, conda
其實任何版本cuda都行,只是alpr.yml中的mxnet版本對應cuda10
[Lincence Plate Detection權重連結](https://drive.google.com/file/d/1KbWPrcSqCCn3XZ3wqlEP45U13wHm2mZS/view?usp=sharing)
[OCR權重連結](https://drive.google.com/open?id=1YbSsDs8FMpEPOYzTW8iPQY_6ESKIhvhr)

## 環境設置
```sh
sudo apt-get install ros-$version-usb-cam
sudo apt-get install ros-$version-cv-bridge
git clone https://github.com/n8886919/YOLO_ALPR
cd YOLO-ALPR
export PYTHONPATH=$PYTHONPATH:~/Desktop/YOLO:$(pwd)
conda env create -f alpr.yml
conda activate alpr.yml
cd licence_plate
python LP_detection.py v2 export --weight (Lincence_Plate_Detection_weight_unzip_path)
cd ../OCR
python OCR v1 export (OCR_weight_unzip_path)
```
## Run Demo
### 車牌偵測
```sh
rosrun usb_cam usb_cam_node
py LP_detection.py v2 video (--topic your_video_topic)
```
### 車牌文字辨識
```sh
py OCR.py v1 video
```
## Troubleshooting
if:
:::danger
[ERROR] [1552911199.414362]: bad callback: <bound method LicencePlateDetectioin._image_callback of <__main__.LicencePlateDetectioin instance at 0x7fd1aa0e1200>>
Traceback (most recent call last):
  File "/opt/ros/melodic/lib/python2.7/dist-packages/rospy/topics.py", line 750, in _invoke_callback
    cb(msg)
  File "LP_detection.py", line 460, in _image_callback
    self.img = self.bridge.imgmsg_to_cv2(img, "bgr8")
  File "/opt/ros/melodic/lib/python2.7/dist-packages/cv_bridge/core.py", line 163, in imgmsg_to_cv2
    dtype, n_channels = self.encoding_to_dtype_with_channels(img_msg.encoding)
  File "/opt/ros/melodic/lib/python2.7/dist-packages/cv_bridge/core.py", line 99, in encoding_to_dtype_with_channels
    return self.cvtype2_to_dtype_with_channels(self.encoding_to_cvtype2(encoding))
  File "/opt/ros/melodic/lib/python2.7/dist-packages/cv_bridge/core.py", line 91, in encoding_to_cvtype2
    from cv_bridge.boost.cv_bridge_boost import getCvType
ImportError: /usr/lib/x86_64-linux-gnu/libblas.so.3: undefined symbol: sgemm_thread_nn
:::
try:
```sh
sudo apt-get remove libopenblas-base
```
