import torch
import pathlib

# 讓 PosixPath 自動轉換成 WindowsPath
temp = pathlib.PosixPath
pathlib.PosixPath = pathlib.WindowsPath

# 讀取並測試模型
model = torch.load("best.pt", map_location="cpu")
torch.save(model, "best_fixed.pt")  # 重新儲存