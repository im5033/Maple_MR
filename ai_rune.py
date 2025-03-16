import torch
import cv2
import numpy as np
from pathlib import Path
from models.common import DetectMultiBackend
from utils.general import non_max_suppression, scale_boxes
from utils.augmentations import letterbox

# 設定模型權重與裝置
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
weights = "best_fixed.pt"
model = DetectMultiBackend(weights, device=device)  # 禁用詳細輸出
model.eval()

# 類別標籤
names = model.names

def detect_objects(img):
    # 調整圖片大小
    img_resized = letterbox(img, 640, stride=32, auto=True)[0]
    img_resized = img_resized[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, HWC to CHW
    img_resized = np.ascontiguousarray(img_resized, dtype=np.float32) / 255.0  # Normalize
    img_tensor = torch.from_numpy(img_resized).unsqueeze(0).to(device)
    
    # 進行推論
    with torch.no_grad():
        pred = model(img_tensor)
    pred = non_max_suppression(pred, 0.25, 0.45, agnostic=False)
    
    # 解析結果
    results = []
    for det in pred:
        if len(det):
            det[:, :4] = scale_boxes(img_tensor.shape[2:], det[:, :4], img.shape).round()
            for *xyxy, conf, cls in det:
                label = names[int(cls)]
                x1, y1, x2, y2 = map(int, xyxy)
                results.append((label, x1, y1, x2, y2))
    
    return results

def ai_slove(img):
    objects = detect_objects(img)
    # 按照 x1 座標進行排序，從左到右
    objects_sorted = sorted(objects, key=lambda obj: obj[1])
    # 提取標籤並整理成列表
    labels = [obj[0] for obj in objects_sorted]
    return labels

# 測試圖片（請自行修改圖片路徑）
image_path = "Q.jpg"
# 讀取圖片
img = cv2.imread(image_path)
objects = detect_objects(img)
# 按照 x1 座標進行排序，從左到右
objects_sorted = sorted(objects, key=lambda obj: obj[1])
# 輸出結果
# for obj in objects_sorted:
#     print(f"Label: {obj[0]}, BBox: ({obj[1]}, {obj[2]}, {obj[3]}, {obj[4]})")
# 提取標籤並整理成列表
labels = [obj[0] for obj in objects_sorted]
# 輸出整理後的結果
print(labels)
