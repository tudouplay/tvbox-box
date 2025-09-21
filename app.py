from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import time
import threading
import json
import os
import random
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tvbox.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# 直播源存储文件
LIVE_SOURCES_FILE = "live_sources.json"
# 备用直播源仓库
BACKUP_REPOSITORIES = [
    "https://raw.githubusercontent.com/tudouplay/tvbox-box/main/live/sources.json",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
    "https://iptvplaylist.net/playlist"
]
# 最大线程数
MAX_WORKERS = 10
# 直播源超时时间(秒)
TIMEOUT = 5
# 定期检查间隔(秒)，这里设置为1小时
CHECK_INTERVAL = 3600

# 初始化直播源数据
live_sources = {
    "updated_at": "",
    "channels": []
}

def load_sources():
    """从文件加载直播源数据"""
    global live_sources
    try:
        if os.path.exists(LIVE_SOURCES_FILE):
            with open(LIVE_SOURCES_FILE, 'r', encoding='utf-8') as f:
                live_sources = json.load(f)
            logger.info(f"Loaded {len(live_sources['channels'])} channels from file")
        else:
            # 如果文件不存在，从仓库加载
            update_sources_from_repositories()
    except Exception as e:
        logger.error(f"Error loading sources: {str(e)}")

def save_sources():
    """保存直播源数据到文件"""
    global live_sources
    try:
        live_sources["updated_at"] = datetime.now().isoformat()
        with open(LIVE_SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(live_sources, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(live_sources['channels'])} channels to file")
    except Exception as e:
        logger.error(f"Error saving sources: {str(e)}")

def check_source_validity(url):
    """检查直播源是否有效"""
    try:
        # 发送HEAD请求检查是否可访问
        response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        return response.status_code in [200, 302, 307]
    except:
        try:
            # 如果HEAD请求失败，尝试GET请求
            response = requests.get(url, timeout=TIMEOUT, stream=True)
            # 检查是否是视频流
            content_type = response.headers.get('Content-Type', '')
            return 'video' in content_type or 'application/octet-stream' in content_type
        except:
            return False

def update_sources_from_repositories():
    """从远程仓库更新直播源"""
    global live_sources
    new_channels = []
    
    for repo in BACKUP_REPOSITORIES:
        try:
            logger.info(f"Fetching sources from {repo}")
            response = requests.get(repo, timeout=10)
            response.encoding = 'utf-8'
            
            if repo.endswith('.m3u'):
                # 处理M3U格式
                channels = parse_m3u(response.text)
                new_channels.extend(channels)
            elif repo.endswith('.json'):
                # 处理JSON格式
                data = response.json()
                if 'channels' in data:
                    new_channels.extend(data['channels'])
            
            logger.info(f"Fetched {len(new_channels)} channels from {repo}")
        except Exception as e:
            logger.error(f"Error fetching from {repo}: {str(e)}")
            continue
    
    # 去重
    unique_channels = {}
    for channel in new_channels:
        key = channel.get('id') or channel.get('name')
        if key and key not in unique_channels:
            unique_channels[key] = channel
    
    live_sources['channels'] = list(unique_channels.values())
    logger.info(f"Total unique channels: {len(live_sources['channels'])}")
    save_sources()
    return len(live_sources['channels'])

def parse_m3u(content):
    """解析M3U格式的直播源"""
    channels = []
    lines = content.splitlines()
    current_channel = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # 解析频道信息
            info_part = line.split('#EXTINF:')[1]
            name = info_part.split(',')[-1].strip()
            current_channel = {
                'id': f"m3u_{hash(name)}",
                'name': name,
                'logo': "",
                'url': "",
                'country': "",
                'category': "",
                'language': "",
                'status': True
            }
        elif not line.startswith('#') and current_channel:
            # 解析直播源URL
            current_channel['url'] = line
            channels.append(current_channel)
            current_channel = None
    
    return channels

def check_and_update_invalid_sources():
    """检查并更新无效的直播源"""
    global live_sources
    logger.info(f"Starting check for invalid sources. Total channels: {len(live_sources['channels'])}")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 为每个频道提交检查任务
        results = list(executor.map(check_channel_validity, live_sources['channels']))
    
    # 更新检查结果
    updated = False
    for i, result in enumerate(results):
        if result is False and live_sources['channels'][i]['status']:
            live_sources['channels'][i]['status'] = False
            # 尝试寻找替代源
            replaced = find_replacement_source(live_sources['channels'][i])
            if replaced:
                logger.info(f"Replaced invalid source for {live_sources['channels'][i]['name']}")
                updated = True
            else:
                logger.warning(f"No replacement found for {live_sources['channels'][i]['name']}")
    
    if updated:
        save_sources()
    
    logger.info("Invalid sources check completed")
    return updated

def check_channel_validity(channel):
    """检查单个频道的有效性"""
    try:
        if 'url' in channel and channel['url']:
            is_valid = check_source_validity(channel['url'])
            if not is_valid:
                logger.warning(f"Invalid source: {channel['name']} - {channel['url']}")
            return is_valid
        return False
    except Exception as e:
        logger.error(f"Error checking {channel.get('name')}: {str(e)}")
        return False

def find_replacement_source(channel):
    """为无效的直播源寻找替代源"""
    # 尝试从其他仓库寻找替代源
    for repo in BACKUP_REPOSITORIES:
        try:
            response = requests.get(repo, timeout=10)
            response.encoding = 'utf-8'
            
            if repo.endswith('.m3u'):
                channels = parse_m3u(response.text)
            elif repo.endswith('.json'):
                data = response.json()
                channels = data.get('channels', [])
            
            # 查找名称相似的频道
            for ch in channels:
                if channel['name'].lower() in ch.get('name', '').lower() or \
                   ch.get('name', '').lower() in channel['name'].lower():
                    # 检查替代源是否有效
                    if check_source_validity(ch['url']):
                        channel['url'] = ch['url']
                        channel['status'] = True
                        return True
        except Exception as e:
            logger.error(f"Error finding replacement from {repo}: {str(e)}")
            continue
    
    return False

def scheduled_update():
    """定时更新直播源"""
    while True:
        logger.info("Starting scheduled update...")
        update_sources_from_repositories()
        check_and_update_invalid_sources()
        logger.info(f"Scheduled update completed. Next update in {CHECK_INTERVAL/3600} hours")
        time.sleep(CHECK_INTERVAL)

# API 路由
@app.route('/api/channels', methods=['GET'])
def get_channels():
    """获取所有电视频道"""
    country = request.args.get('country')
    category = request.args.get('category')
    language = request.args.get('language')
    search = request.args.get('search')
    
    filtered = live_sources['channels']
    
    # 过滤国家
    if country:
        filtered = [ch for ch in filtered if ch.get('country', '').lower() == country.lower()]
    
    # 过滤分类
    if category:
        filtered = [ch for ch in filtered if ch.get('category', '').lower() == category.lower()]
    
    # 过滤语言
    if language:
        filtered = [ch for ch in filtered if ch.get('language', '').lower() == language.lower()]
    
    # 搜索
    if search:
        search_term = search.lower()
        filtered = [ch for ch in filtered if search_term in ch.get('name', '').lower()]
    
    return jsonify({
        'total': len(filtered),
        'updated_at': live_sources['updated_at'],
        'channels': filtered
    })

@app.route('/api/channel/<channel_id>', methods=['GET'])
def get_channel(channel_id):
    """获取单个频道详情"""
    for channel in live_sources['channels']:
        if channel.get('id') == channel_id:
            return jsonify(channel)
    return jsonify({'error': 'Channel not found'}), 404

@app.route('/api/update', methods=['POST'])
def manual_update():
    """手动触发更新"""
    count = update_sources_from_repositories()
    return jsonify({'message': f'Updated {count} channels', 'updated_at': live_sources['updated_at']})

@app.route('/api/check', methods=['POST'])
def manual_check():
    """手动触发检查无效源"""
    updated = check_and_update_invalid_sources()
    return jsonify({
        'message': f'Invalid sources checked. {"Some sources were updated" if updated else "No updates needed"}',
        'updated_at': live_sources['updated_at']
    })

@app.route('/api/countries', methods=['GET'])
def get_countries():
    """获取所有国家列表"""
    countries = set()
    for channel in live_sources['channels']:
        if channel.get('country'):
            countries.add(channel['country'])
    return jsonify(sorted(list(countries)))

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """获取所有分类列表"""
    categories = set()
    for channel in live_sources['channels']:
        if channel.get('category'):
            categories.add(channel['category'])
    return jsonify(sorted(list(categories)))

@app.route('/api/languages', methods=['GET'])
def get_languages():
    """获取所有语言列表"""
    languages = set()
    for channel in live_sources['channels']:
        if channel.get('language'):
            languages.add(channel['language'])
    return jsonify(sorted(list(languages)))

if __name__ == '__main__':
    # 初始化加载
    load_sources()
    
    # 启动定时更新线程
    update_thread = threading.Thread(target=scheduled_update, daemon=True)
    update_thread.start()
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=5000, debug=True)
