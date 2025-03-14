import cv2
import os
import numpy as np
import mss
import win32gui
import serial
import time
import keyboard
import asyncio
import random
import pyautogui
import pygame
import concurrent.futures
from collections import deque
from rune_slover import find_arrow_directions

window_name = "MapleStory"
# 取得腳本運行目錄
script_dir = os.path.dirname(os.path.abspath(__file__))

def asset_path(filename):
    return os.path.join(script_dir, "assest", filename)

def music_path(filename):
    return os.path.join(script_dir, "assest", "music", filename)

def warning_path(filename):
    return os.path.join(script_dir, "assest", "warning", filename)

def polygraph_path(filename):
    return os.path.join(script_dir, "assest", "polygraph", filename)

# 預先載入模板
templates = {
    "minimap_tl": cv2.imread(asset_path("minimap_tl_template.png")),
    "minimap_br": cv2.imread(asset_path("minimap_br_template.png")),
    "player": cv2.imread(asset_path("player_template.png")),
    "other": cv2.imread(asset_path("other_template.png")),
    "rune": cv2.imread(asset_path("rune_template.png")),
    "rune_buff": cv2.imread(asset_path("rune_buff_template.png")),
    "map_boss": cv2.imread(warning_path("map_boss.png"))
}

warning_templates = [
    cv2.imread(polygraph_path("polygraph1.png")),
    cv2.imread(polygraph_path("polygraph2.png")),
    cv2.imread(polygraph_path("polygraph3.png")),
    cv2.imread(polygraph_path("polygraph4.png")),
    cv2.imread(warning_path("black_house.png")),
    cv2.imread(warning_path("die.png")),
    cv2.imread(warning_path("gm1.png")),
    cv2.imread(warning_path("gm2.png"))
]

# 確保所有模板載入成功
for key, img in templates.items():
    if img is None:
        raise ValueError(f"Error: Unable to load template {key}")
for i, img in enumerate(warning_templates):
    if img is None:
        raise ValueError(f"Error: Unable to load warning template {i}")

# 音效路徑
danger_sound_path = music_path("danger.mp3")
rune_fail_sound_path = music_path("rune_fail.mp3")


# 設定串口參數
arduino = serial.Serial(port='COM9', baudrate=9600, timeout=1)
rune_buff_location = (-1,-1)
paused = True  # 控制是否暫停的標誌 
px, py =0,0
rx, ry = -1, -1
update_screen_interval = 0.01
minimap = None
danger_sound_playing = False  # 追蹤是否正在播放
volume = 0.1  # 預設音量（10%）
attempts = 0 # 解輪失敗次數
Mage = False
use_skill = True 
px_left, px_right = 50, 140 
py_top, py_bottom = 40, 45
random_direction = 1 / (px_right - px_left + random.randint(10, 20))  # 隨機決定人物往左或右方向移動的機率
switch_down_count, switch_up_count = -3, -3 # 調大可以不上下跳
random_updown_count = (-3,-2) 
random_up = 5
random_down = 5

# 初始技能冷卻時間
skill_cooldowns = {
    "home":250,
    "delete": 250,
    "ctrl": 8,
    "shift": 10,
}
# skill_cooldowns = {
    # "7": 180,
    # "6": 120,
    # "home":250,
    # "delete": 250,
    # "e": 30,
    # "a": 60,
    # "f": 92,
    # "s": 60,
    # "v": 120,    
    # "w": 6
# }


# 初始化 pygame 混音器
pygame.mixer.init()

# 設定音量
pygame.mixer.music.set_volume(volume)

time.sleep(2)  # 等待 Arduino 初始化

def send_command(command):
    arduino.write(command.encode())  # 發送命令
        
def get_window_rect(window_name):
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        # 檢查視窗是否最小化
        if win32gui.IsIconic(hwnd):
            print("Window is minimized!")
            return None
        return rect
    return None

def capture_window(window_name):
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd:
        # 檢查視窗是否最小化
        if win32gui.IsIconic(hwnd):
            print("Window is minimized!")
            return None

        # 檢查視窗是否為前景視窗
        if win32gui.GetForegroundWindow() != hwnd:
            print("Window is not in the foreground!")
            return None
        
        rect = win32gui.GetWindowRect(hwnd)
        if rect is None:
            print("Window not found!")
            return None

        x, y, x1, y1 = rect
        width, height = x1 - x, y1 - y

        with mss.mss() as sct:
            screenshot = sct.grab({'left': x, 'top': y, 'width': width, 'height': height})
            img = np.array(screenshot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    else:
        print("Window not found!")
        return None

def match_template(image, template, threshold=0.75, roi=None):
    if image is None or template is None:
        return (-1, -1), 0
    
    # 限制 ROI 範圍（方法 4）
    if roi:
        x1, y1, x2, y2 = roi
        image = image[y1:y2, x1:x2]
    
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    threshold_result = result >= threshold
    locations = np.where(threshold_result)
    num_matches = len(locations[0])
    
    if num_matches > 0:
        _, _, _, max_loc = cv2.minMaxLoc(result)
        return max_loc, num_matches
    else:
        return (-1, -1), 0

# 記錄每個技能的上次使用時間
last_used_times = {key: time.time() - cooldown for key, cooldown in skill_cooldowns.items()}

async def move_player():
    global px ,py
    global switch_down_count, switch_up_count
    num_last_moves = 0
    last_px, last_py =  px, py
    
    while True:
        if not paused:
            current_time = time.time()  # 當前時間
            # 如果人物沒有移動，累積次數
            if last_px == px and last_py == py:
                num_last_moves += 1
            else:
                num_last_moves = 0  # 只要有移動就重置計數

            # 若計數達 5 次，視為卡住
            if num_last_moves >= 5:
                print("人物卡住不動，向下2秒脫困")
                send_command("down_d")
                await asyncio.sleep(2)  # 非同步等待
                send_command("down_u")
                num_last_moves = 0  # 重置卡住計數
                last_px, last_py = 0, 0  # 避免重複觸發

            # 更新上一次的位置
            last_px, last_py = px, py
                
            max_d = (px_right - px_left) / 2
            d_left = abs(px - px_left)
            d_right = abs(px - px_right)
            
            P = random_direction * min(d_left, d_right) / max_d  # 計算機率

            if px > px_right or random.random() < P:
                print("Left")
                await asyncio.sleep(0.1)
                await attack("left")
                await asyncio.sleep(0.3)
                continue
            elif px < px_left or random.random() < P:
                print("Right")
                await asyncio.sleep(0.1)
                await attack("right")
                await asyncio.sleep(0.3)
                continue

            if use_skill:
                # 檢查技能是否可以使用
                used_skill = False  # 用來判斷這回合是否有用技能
                for skill, cooldown in skill_cooldowns.items():
                    time_since_last_use = current_time - last_used_times[skill]
                    remaining_cooldown = max(0, cooldown - time_since_last_use)

                    # 打印技能的冷卻時間
                    print(f"技能 {skill} 剩餘冷卻時間: {remaining_cooldown:.2f} 秒")

                    # 如果冷卻時間已經過了
                    if remaining_cooldown == 0:
                        print(f"使用技能 {skill}")
                        await asyncio.sleep(0.5)  # 非同步等待
                        send_command(skill)
                        last_used_times[skill] = current_time  # 更新該技能的最後使用時間
                        await asyncio.sleep(0.6)  # 等待技能使用的時間
                        used_skill = True  # 設定為有使用技能
                        break
                # 如果沒有使用技能，等待 0.5 秒
                if not used_skill:
                    await asyncio.sleep(0.5)
            
            if py < py_top :
                switch_down_count += 1
            if py > py_bottom:
                switch_up_count += 1

            await attack()
            await asyncio.sleep(0.5)

            
            if switch_down_count > (random.random()*random_down) :
                print("Down")
                await asyncio.sleep(0.5)
                send_command("down_d")
                await asyncio.sleep(0.05)  # 非同步等待
                send_command("alt")
                await asyncio.sleep(0.05)
                send_command("down_u")
                await asyncio.sleep(1)  # 非同步等待
                switch_down_count = random.randint(*random_updown_count)
        
            if switch_up_count > (random.random()*random_up):
                if px_left <= px <= px_right:
                    await asyncio.sleep(0.5)
                    print("Up")
                    send_command("x")
                    await asyncio.sleep(1)  # 非同步等待
                else:
                    continue
                if py > py_bottom :
                    continue
                else:
                    switch_up_count = random.randint(*random_updown_count) # 更容易上跳

            print(f"{switch_down_count} {switch_up_count}")

        else:
            await asyncio.sleep(0.8)  # 避免CPU占用過高

last_direction = None
async def attack(direction = "None", attack_command = "q"):
    global last_direction
    flash_command = "shift"    

    if last_direction is None:  # 第一次呼叫時初始化
        last_direction = random.choice(["left", "right"])
    if direction != "None":
        last_direction = direction # 只在有輸入 direction 時才改變

    if Mage == True:
        send_command(f"{last_direction}_d")
        await asyncio.sleep(0.05)  # 非同步等待
        send_command(flash_command)
        await asyncio.sleep(0.05)  # 非同步等待
        send_command(f"{last_direction}_u")
        await asyncio.sleep(0.3)  # 非同步等待
        send_command(attack_command)
    else:
        send_command(f"{last_direction}_d")
        await asyncio.sleep(0.1)  # 非同步等待
        send_command("alt")
        await asyncio.sleep(0.1)  # 非同步等待
        send_command("alt")
        await asyncio.sleep(0.05)
        send_command(f"{last_direction}_u")
        await asyncio.sleep(0.05)  # 非同步等待
        send_command(attack_command) 

    await asyncio.sleep(0.05)  # 非同步等待   
    send_command("all")

async def process_templates(image, templates, threshold=0.75, roi=None):
    """多執行緒並行匹配多個模板，提高效率"""
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            key: loop.run_in_executor(executor, match_template, image, template, threshold, roi)
            for key, template in templates.items()
        }
        results = await asyncio.gather(*futures.values())
    return dict(zip(templates.keys(), results))

async def update_screen():
    global paused
    global danger_sound_playing, volume
    global px, py, rx, ry, rune_buff_location
    global minimap
    counts = -1

    while True:
        screenshot = capture_window(window_name)
        if screenshot is None:
            paused = True
            await asyncio.sleep(2)
            continue  # 若視窗未找到，繼續下一次迴圈

        try:
            counts += 1
            # 🔹 在整張 screenshot 中一次找出 minimap 邊界
            minimap_results = await process_templates(
                screenshot, {"minimap_tl": templates["minimap_tl"], "minimap_br": templates["minimap_br"]}, 0.5
            )
            (x1, y1), _ = minimap_results["minimap_tl"]
            (x2, y2), _ = minimap_results["minimap_br"]

            if x2 != -1:
                x2 += 20  # 可能要微調

            if x1 >= x2 or y1 >= y2 or x2 > 683 or y2 > 384: # 超過 1366*768 的一半
                print("Error: Invalid minimap coordinates.")
                await asyncio.sleep(update_screen_interval)
                continue

            minimap = screenshot[y1:y2, x1:x2]  # 截取 minimap 區域

            # 🔹 在 minimap 上一次性匹配多個目標
            minimap_targets = await process_templates(minimap, {
                "player": templates["player"],
                "rune": templates["rune"],
                "other": templates["other"]
            })

            # 取得匹配結果
            (px, py), _ = minimap_targets["player"]
            (rx, ry), _ = minimap_targets["rune"]
            _, other_count = minimap_targets["other"]

            if (px, py) != (-1, -1):
                print(f"Player Coordinates: ({px}, {py}) {counts}")
            else:
                print("Error: Invalid player coordinates.")
                await asyncio.sleep(update_screen_interval)
                continue

            # 🔹 獨立執行 `rune_buff` 和 `boss` 檢查
            if counts % 30 == 0:  
                asyncio.create_task(scan_rune_and_boss(screenshot))

            # 🔹 偵測到其他玩家或 Boss，觸發警報
            if other_count >= 2 and paused == False:
                print(f"Other player: {other_count}!")
                if not danger_sound_playing:
                    pygame.mixer.music.load(danger_sound_path)
                    pygame.mixer.music.play(loops=-1)
                    pygame.mixer.music.set_volume(volume)
                    danger_sound_playing = True
                await asyncio.sleep(update_screen_interval)
                continue

            # 🔹 警告標誌掃描（獨立執行緒，避免影響主要邏輯）
            if counts % 20 == 0:
                asyncio.create_task(scan_warnings(screenshot))

            await asyncio.sleep(update_screen_interval)
        except Exception as e:
            print(f"Error in processing: {e}")
            await asyncio.sleep(update_screen_interval)

        if counts >= 1000:
            counts = 0


async def scan_rune_and_boss(screenshot):
    """獨立執行 Rune Buff 與 Boss 掃描，避免影響主要迴圈"""
    global rune_buff_location, danger_sound_playing
    try:
        screenshot_targets = await process_templates(screenshot, {
            "rune_buff": templates["rune_buff"],
            "map_boss": templates["map_boss"]
        })
        rune_buff_location, _ = screenshot_targets["rune_buff"]
        boss_path, _ = screenshot_targets["map_boss"]

        if boss_path != (-1, -1) and boss_path[1] < 50: # Boss只會在上面
            print(f"Boss detected at {boss_path}")
            if not danger_sound_playing and paused == False:
                pygame.mixer.music.load(danger_sound_path)
                pygame.mixer.music.play(loops=-1)
                pygame.mixer.music.set_volume(volume)
                danger_sound_playing = True
            return
    except Exception as e:
        print(f"Error in scanning rune and boss: {e}")

warning_history = deque(maxlen=3)  # 記錄最近 3 次偵測結果
async def scan_warnings(screenshot):
    """獨立執行警告圖標掃描，減少 `update_screen()` 的負擔"""
    global paused, danger_sound_playing
    try:
        warning_results = await process_templates(screenshot, {
            f"warning_{i}": path for i, path in enumerate(warning_templates)
        })
        detected = False  # 記錄這幀是否有偵測到警告

        for key, (warning_path, _) in warning_results.items():
            if warning_path != (-1, -1):
                print(f"Warning detected: {key}")
                detected = True  # 記錄偵測到警告
                break

        warning_history.append(detected)

        # 只有當最近 3 次都偵測到警告時才觸發
        if all(warning_history):
            paused = True
            if not danger_sound_playing:
                pygame.mixer.music.load(danger_sound_path)
                pygame.mixer.music.play(loops=-1)
                pygame.mixer.music.set_volume(volume)
                danger_sound_playing = True
            return
    except Exception as e:
        print(f"Error in scanning warnings: {e}")

async def find_rune():
    while True:
        global rx, ry
        global paused
        if not paused and rx!= -1 and ry!= -1 and rune_buff_location == (-1, -1):
            print(f"Rune Coordinates: ({rx}, {ry})")
            # 只有當需要移動時才暫停
            if px != rx or not (ry - 1 <= py <= ry + 1):
                paused = True
            await move_to_point(rx, ry, True)
            await asyncio.sleep(0.1)  # 等待座標更新
            await detail_rune()
            # 重置數值 & 解除暫停狀態
            rx, ry = (-1, -1)  # 重置符文座標
            paused = False  # 讓程式恢復執行
        else:
            #print("Error: Invalid rune coordinates.")
            await asyncio.sleep(update_screen_interval)
            continue
        await asyncio.sleep(update_screen_interval)

async def detect_pressKeys():
    global danger_sound_playing
    while True:
        if keyboard.is_pressed('F10'):
            global paused
            paused = not paused
            print(f"Pause: {paused}")
            time.sleep(0.5)  # 防止重複觸發
        if keyboard.is_pressed('F11'):
            await exit_cashshop()
            time.sleep(0.5)  # 防止重複觸發
        if keyboard.is_pressed('F9'):
            await move_to_point(84,11)
            time.sleep(0.5)  # 防止重複觸發
        if keyboard.is_pressed('F12'):
            if danger_sound_playing:
                pygame.mixer.music.stop()  # 停止播放
                danger_sound_playing = False
                print("警報解除")
            else:
                pygame.mixer.music.load(danger_sound_path)  # 載入音樂
                pygame.mixer.music.play()  # 播放音樂
                pygame.mixer.music.play(loops=-1)  # 循環播放
                pygame.mixer.music.set_volume(volume)  # 設定音量
                danger_sound_playing = True
                print(f"發生警報")
            time.sleep(0.5)  # 防止重複觸發

        await asyncio.sleep(0.05)

async def move_to_point(current_x, current_y, move_to_rune = False):
    print("Move to point")
    global paused
    paused = True
    #await asyncio.sleep(1) # 等待技能放完
    while not current_x == px or not (current_y - 1 <= py <= current_y + 1):
        while not current_x == px : # 只有 px = rx 時才停止
            if move_to_rune and rx == -1:
                return
            print("X軸移動中")
            if px > current_x:
                distance = px - current_x
                if distance >= 20:
                    send_command("left")
                    await asyncio.sleep(0.05)
                    await attack("left")
                    await asyncio.sleep(0.4)
                elif 20 >= distance >= 5:
                    send_command("left_d")
                    # 用 while 循環處理 px 達到 current_x + 5 時停止
                    max_attempts = 20  # 設定最大循環次數，避免卡住
                    attempts = 0
                    while px >= current_x + 5 and attempts < max_attempts:
                        await asyncio.sleep(0.01)  # 等待檢查
                        attempts += 1
                    send_command("left_u")
                    await asyncio.sleep(0.1)
                else:
                    send_command("left")
                    print("left")
                    await asyncio.sleep(0.2)

            elif px < current_x:
                distance = current_x - px  # 直接計算位置差距
                if distance >= 20:
                    send_command("right")
                    await asyncio.sleep(0.05)
                    await attack("right")
                    await asyncio.sleep(0.4)
                elif 20 >= distance >= 5:
                    send_command("right_d")
                    # 用 while 循環處理 px 小於 current_x - 5 時停止
                    max_attempts = 20  # 設定最大循環次數，避免卡住
                    attempts = 0
                    while px <= current_x - 5 and attempts < max_attempts:
                        await asyncio.sleep(0.01)  # 等待檢查
                        attempts += 1
                    send_command("right_u")
                    await asyncio.sleep(0.1)
                else:
                    send_command("right")
                    print("right")
                    await asyncio.sleep(0.2)
        print("X軸移動結束")
        await asyncio.sleep(0.3)
        while not (current_y - 1 <= py <= current_y + 1) : # 只有 py = ry 時才停止
            if move_to_rune and ry == -1:
                return
            print("Y軸移動中")
            if py > current_y:
                send_command("x")
                await asyncio.sleep(3)  # 非同步等待
            elif py < current_y:
                send_command("down_d")
                await asyncio.sleep(0.05)  # 非同步等待
                send_command("alt")
                await asyncio.sleep(0.05)
                send_command("down_u")
                await asyncio.sleep(3)  # 非同步等待
        print("Y軸移動結束")
        await asyncio.sleep(0.3)
    print("XY移動結束")
    if not move_to_rune:
        paused = False


async def detail_rune():
    global attempts, rune_buff_location
    
    while attempts <= 3 :
        await asyncio.sleep(0.2)
        send_command("space")
        await asyncio.sleep(0.2)

        screenshot = capture_window(window_name)
        data = find_arrow_directions(screenshot)
        if len(data) == 4:
            directions = [direction for direction, _ in data]
            print(f"Directions: {directions}")
            await asyncio.sleep(1)
            for d in directions:
                send_command(d)
                await asyncio.sleep(0.2)
            
            await asyncio.sleep(1)

            check_screenshot = capture_window(window_name)
            rune_buff_location, _ = match_template(check_screenshot, templates["rune_buff"])
            if rune_buff_location != (-1, -1):
                print("Rune has been solved.")
                cv2.imwrite(f"rune/screenshot_{str(int(time.time()))}.png", screenshot)
                attempts = 0
                break
            else:
                print("Trying again...")
                cv2.imwrite(f"rune/fail/screenshot_{str(int(time.time()))}.png", screenshot)
                pygame.mixer.music.load(rune_fail_sound_path)  # 載入音樂
                pygame.mixer.music.play()  # 播放音樂
                pygame.mixer.music.set_volume(volume)  # 設定音量
            await asyncio.sleep(1)
        else:
            print("Rune unidentifiable. Trying again...")
            cv2.imwrite(f"rune/fail/screenshot_{str(int(time.time()))}.png", screenshot)
            pygame.mixer.music.load(rune_fail_sound_path)  # 載入音樂
            pygame.mixer.music.play()  # 播放音樂
            pygame.mixer.music.set_volume(volume)  # 設定音量
            await asyncio.sleep(3)
            attempts += 1
            if attempts > 3:
                send_command("scroll lock")
                attempts = 0
                await asyncio.sleep(5)
                await exit_cashshop()
                await asyncio.sleep(3)

async def exit_cashshop():
        hwnd = win32gui.FindWindow(None, window_name)
        rect = win32gui.GetWindowRect(hwnd)
        if rect is None:
            print("Window not found!")
            return None
    
        x, _, _, y = rect
        pyautogui.click(x+60, y-25)
        await asyncio.sleep(1)


async def main():
    # 啟動獨立的異步任務
    task1 = asyncio.create_task(update_screen())
    task2 = asyncio.create_task(move_player())
    task3 = asyncio.create_task(detect_pressKeys())
    task6 = asyncio.create_task(find_rune())

    await asyncio.gather(task1, task2, task3, task6)

if __name__ == "__main__":
    asyncio.run(main())
