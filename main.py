from fastapi import FastAPI, Request, BackgroundTasks, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import yt_dlp
import os
import asyncio
import datetime
import humanize
import logging
from urllib.parse import quote
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
# 挂载下载目录为静态文件
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

templates = Jinja2Templates(directory="templates")

# 存储下载视频的信息
videos = []
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def download_progress_hook(d):
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '0%')
        speed = d.get('_speed_str', 'N/A')
        logger.info(f"Download progress: {progress}, Speed: {speed}")

async def download_video(url: str):
    logger.info(f"Starting download for URL: {url}")
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [download_progress_hook],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Extracting video info...")
            info = ydl.extract_info(url, download=True)
            
            # 处理文件名，移除不安全字符
            safe_title = re.sub(r'[^\w\s-]', '', info['title'])
            safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
            filename = f"{safe_title}.{info['ext']}"
            original_file = os.path.join(DOWNLOAD_DIR, f"{info['title']}.{info['ext']}")
            safe_file = os.path.join(DOWNLOAD_DIR, filename)
            
            # 如果文件名不同，重命名文件
            if original_file != safe_file and os.path.exists(original_file):
                os.rename(original_file, safe_file)
            
            file_path = safe_file
            logger.info(f"Download completed: {filename}")
            
            video_info = {
                'title': info['title'],
                'duration': str(datetime.timedelta(seconds=int(info['duration']))),
                'author': info['uploader'],
                'description': info.get('description', '')[:200] + '...',
                'file_path': f"/api/download/{quote(filename)}",  # 使用新的下载接口
                'file_size': humanize.naturalsize(os.path.getsize(file_path)),
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'download_path': file_path,
                'safe_filename': filename
            }
            videos.append(video_info)
            return video_info
    except Exception as e:
        logger.error(f"Error during download: {str(e)}")
        return {"error": str(e)}

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "videos": videos
    })

@app.post("/download")
async def download(background_tasks: BackgroundTasks, url: str = Form(...)):
    logger.info(f"Received download request for URL: {url}")
    try:
        # 立即启动下载任务
        video_info = await download_video(url)
        if "error" in video_info:
            return {"message": video_info["error"], "status": "error"}
        return {"message": "Download completed", "status": "success", "video": video_info}
    except Exception as e:
        logger.error(f"Error starting download: {str(e)}")
        return {"message": str(e), "status": "error"}

@app.get("/videos")
async def get_videos():
    return {"videos": videos}

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    try:
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(file_path):
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type='application/octet-stream'  # 强制下载
            )
        return {"error": "File not found"}
    except Exception as e:
        logger.error(f"Error serving file: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)