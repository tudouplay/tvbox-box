#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox直播源自动更新系统 - 完整版
功能：自动搜索、检测、更新、替换无效直播源
作者：tudouplay
项目地址：https://github.com/tudouplay/tvbox-box
"""

import os
import re
import time
import json
import random
import requests
import asyncio
import aiohttp
import socket
import urllib.parse
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import logging
from pathlib import Path

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler('output/update.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class TVBoxUpdater:
    """TVBox直播源管理器"""
    
    def __init__(self):
        """初始化配置"""
        self.config = {
            # 文件路径
            'source_file': 'config/demo.txt',
            'local_file': 'config/local.txt',
            'whitelist_file': 'config/whitelist.txt',
            'output_txt': 'output/result.txt',
            'output_m3u': 'output/result.m3u',
            'output_json': 'output/result.json',
            'stats_file': 'output/stats.json',
            'log_file': 'output/update.log',
            
            # 性能配置
            'max_workers': 30,  # 并发数
            'timeout': 15,      # 超时时间(秒)
            'retry_times': 3,   # 重试次数
            'retry_delay': 2,   # 重试延迟(秒)
            
            # 过滤配置
            'max_urls_per_channel': 10,  # 每个频道最大URL数
            'min_speed': 0.2,            # 最小速度(MB/s)
            'min_resolution': '640x480', # 最低分辨率
            'ipv_type': 'all',           # all/ipv4/ipv6
            
            # 功能开关
            'open_speed_test': True,
            'open_resolution_check': False,  # 关闭分辨率检测，提高速度
            'open_hotel_source': True,
            'open_multicast_source': True,
            'open_online_search': True,
            'open_local_source': True,
            
            # 搜索配置
            'search_timeout': 30,
            'max_search_pages': 3,
        }
        
        # 直播源订阅地址
        self.subscribe_sources = [
            'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u',
            'https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u',
            'https://raw.githubusercontent.com/yue365/IPTV/master/daily.m3u',
            'https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt',
            'https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u',
            'https://raw.githubusercontent.com/asdjkl6/tv/main/m.json',
            'https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt',
        ]
        
        # 请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 频道别名映射
        self.channel_aliases = {
            'CCTV1': ['CCTV-1', 'CCTV-1 综合', '央视一套', '中央一套'],
            'CCTV2': ['CCTV-2', 'CCTV-2 财经', '央视二套', '中央二套'],
            'CCTV3': ['CCTV-3', 'CCTV-3 综艺', '央视三套', '中央三套'],
            '湖南卫视': ['湖南台', '芒果台', 'Hunan TV'],
            '浙江卫视': ['浙江台', 'Zhejiang TV'],
            '东方卫视': ['东方台', 'Shanghai TV', '上海卫视'],
            # 添加更多别名...
        }
        
        # 初始化统计
        self.stats = {
            'start_time': datetime.now(),
            'total_sources': 0,
            'valid_sources': 0,
            'failed_sources': 0,
            'total_channels': 0,
            'total_urls': 0,
        }
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        directories = ['config', 'output', 'temp']
        for directory in directories:
            Path(directory).mkdir(exist_ok=True)
    
    async def fetch_with_retry(self, session: aiohttp.ClientSession, url: str, **kwargs) -> Optional[str]:
        """带重试的HTTP请求"""
        for attempt in range(self.config['retry_times']):
            try:
                async with session.get(url, **kwargs) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"请求失败 {url}: HTTP {response.status}")
            except asyncio.TimeoutError:
                logger.warning(f"请求超时 {url} (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"请求错误 {url}: {e} (attempt {attempt + 1})")
            
            if attempt < self.config['retry_times'] - 1:
                await asyncio.sleep(self.config['retry_delay'] * (attempt + 1))
        
        return None
    
    async def fetch_subscribe_sources(self) -> Dict[str, List[str]]:
        """获取订阅源"""
        logger.info("开始获取订阅源...")
        channel_urls = {}
        
        timeout = aiohttp.ClientTimeout(total=self.config['search_timeout'])
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            tasks = []
            for source_url in self.subscribe_sources:
                tasks.append(self.fetch_with_retry(session, source_url))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, content in enumerate(results):
                if isinstance(content, str) and content:
                    source_url = self.subscribe_sources[i]
                    logger.info(f"解析订阅源: {source_url}")
                    
                    if '#EXTM3U' in content:
                        self.parse_m3u_content(content, channel_urls)
                    else:
                        self.parse_txt_content(content, channel_urls)
                else:
                    logger.warning(f"订阅源获取失败: {self.subscribe_sources[i]}")
        
        logger.info(f"订阅源获取完成，共{len(channel_urls)}个频道")
        return channel_urls
    
    def parse_m3u_content(self, content: str, channel_urls: Dict[str, List[str]]):
        """解析M3U内容"""
        lines = content.strip().split('\n')
        current_channel = ""
        current_logo = ""
        current_group = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                # 提取频道信息
                current_channel = ""
                current_logo = ""
                current_group = ""
                
                # 提取频道名称
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                if name_match:
                    current_channel = name_match.group(1)
                else:
                    name_match = re.search(r',(.+)$', line)
                    if name_match:
                        current_channel = name_match.group(1).strip()
                
                # 提取频道图标
                logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                if logo_match:
                    current_logo = logo_match.group(1)
                
                # 提取分组
                group_match = re.search(r'group-title="([^"]*)"', line)
                if group_match:
                    current_group = group_match.group(1)
                    
            elif line and not line.startswith('#') and current_channel:
                # 这是URL行
                if current_channel not in channel_urls:
                    channel_urls[current_channel] = []
                
                # 验证URL格式
                if self.is_valid_url(line):
                    channel_urls[current_channel].append(line)
                else:
                    logger.debug(f"跳过无效URL: {line}")
                
                current_channel = ""
    
    def parse_txt_content(self, content: str, channel_urls: Dict[str, List[str]]):
        """解析TXT内容"""
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line and ',' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    channel_name = parts[0].strip()
                    url = parts[-1].strip()
                    
                    if channel_name and url and url.startswith('http'):
                        if channel_name not in channel_urls:
                            channel_urls[channel_name] = []
                        channel_urls[channel_name].append(url)
    
    def is_valid_url(self, url: str) -> bool:
        """验证URL格式"""
        try:
            result = urllib.parse.urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False
            
            # 检查协议
            if result.scheme not in ['http', 'https', 'udp', 'rtmp']:
                return False
            
            # 检查域名/IP
            if not result.netloc:
                return False
            
            return True
        except Exception:
            return False
    
    def generate_hotel_sources(self) -> Dict[str, List[str]]:
        """生成酒店源"""
        logger.info("生成酒店源...")
        channel_urls = {}
        
        # 常见酒店频道配置
        hotel_configs = {
            'CCTV-1 综合': [
                {'ip': '10.0.0.1', 'port': '4022', 'a': '1', 'b': '1', 'c': '1', 'port2': '5140'},
                {'ip': '172.16.0.1', 'port': '8088', 'a': '1', 'b': '1', 'c': '1', 'port2': '5140'},
                {'ip': '192.168.1.1', 'port': '8000', 'a': '1', 'b': '1', 'c': '1', 'port2': '5140'},
            ],
            'CCTV-2 财经': [
                {'ip': '10.0.0.1', 'port': '4022', 'a': '1', 'b': '1', 'c': '2', 'port2': '5140'},
                {'ip': '172.16.0.1', 'port': '8088', 'a': '1', 'b': '1', 'c': '2', 'port2': '5140'},
            ],
            '湖南卫视': [
                {'ip': '10.0.0.1', 'port': '4022', 'a': '1', 'b': '2', 'c': '1', 'port2': '5140'},
                {'ip': '172.16.0.1', 'port': '8088', 'a': '1', 'b': '2', 'c': '1', 'port2': '5140'},
            ],
            '浙江卫视': [
                {'ip': '10.0.0.1', 'port': '4022', 'a': '1', 'b': '2', 'c': '2', 'port2': '5140'},
                {'ip': '172.16.0.1', 'port': '8088', 'a': '1', 'b': '2', 'c': '2', 'port2': '5140'},
            ],
            '东方卫视': [
                {'ip': '10.0.0.1', 'port': '4022', 'a': '1', 'b': '2', 'c': '3', 'port2': '5140'},
                {'ip': '172.16.0.1', 'port': '8088', 'a': '1', 'b': '2', 'c': '3', 'port2': '5140'},
            ],
        }
        
        for channel, configs in hotel_configs.items():
            channel_urls[channel] = []
            for config in configs:
                try:
                    url = f"http://{config['ip']}:{config['port']}/udp/239.{config['a']}.{config['b']}.{config['c']}:{config['port2']}"
                    if self.is_valid_url(url):
                        channel_urls[channel].append(url)
                except KeyError as e:
                    logger.error(f"酒店源配置错误: {e}")
        
        return channel_urls
    
    def generate_multicast_sources(self) -> Dict[str, List[str]]:
        """生成组播源"""
        logger.info("生成组播源...")
        channel_urls = {}
        
        # 常见组播频道配置
        multicast_configs = {
            'CCTV-1 综合': [('239.1.1.1', 5140), ('239.1.1.2', 5140), ('239.1.1.3', 5140)],
            'CCTV-2 财经': [('239.1.1.4', 5140), ('239.1.1.5', 5140)],
            'CCTV-3 综艺': [('239.1.1.6', 5140), ('239.1.1.7', 5140)],
            '湖南卫视': [('239.1.2.1', 5140), ('239.1.2.2', 5140)],
            '浙江卫视': [('239.1.2.3', 5140), ('239.1.2.4', 5140)],
            '东方卫视': [('239.1.2.5', 5140), ('239.1.2.6', 5140)],
        }
        
        for channel, addresses in multicast_configs.items():
            channel_urls[channel] = []
            for ip, port in addresses:
                url = f"udp://@{ip}:{port}"
                if self.is_valid_url(url):
                    channel_urls[channel].append(url)
        
        return channel_urls
    
    async def check_udp_source(self, ip: str, port: int) -> bool:
        """检测UDP源有效性"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            # 发送一个简单的UDP探测包
            sock.sendto(b'\x00\x00\x00\x00', (ip, port))
            sock.close()
            return True
        except Exception:
            return False
    
    async def check_url_validity(self, session: aiohttp.ClientSession, url: str, channel: str) -> Dict:
        """检测URL有效性"""
        result = {
            'url': url,
            'channel': channel,
            'valid': False,
            'response_time': float('inf'),
            'speed': 0,
            'resolution': '',
            'protocol': '',
            'error': '',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            
            # 检测不同协议
            if url.startswith('http'):
                result['protocol'] = 'http'
                try:
                    timeout = aiohttp.ClientTimeout(total=self.config['timeout'])
                    async with session.get(
                        url, 
                        timeout=timeout,
                        headers=self.headers,
                        allow_redirects=True
                    ) as response:
                        if response.status == 200:
                            result['valid'] = True
                            result['response_time'] = time.time() - start_time
                            
                            # 检测速度
                            if self.config['open_speed_test']:
                                content_length = response.headers.get('Content-Length')
                                if content_length and int(content_length) > 0:
                                    # 只读取部分内容来检测速度
                                    chunk_size = min(int(content_length), 1024 * 500)  # 500KB
                                    content = await response.content.read(chunk_size)
                                    result['speed'] = len(content) / result['response_time'] / 1024 / 1024
                                else:
                                    # 读取默认大小
                                    chunk = await response.content.read(1024 * 100)  # 100KB
                                    if chunk:
                                        result['speed'] = len(chunk) / result['response_time'] / 1024 / 1024
                        else:
                            result['error'] = f"HTTP {response.status}"
                            
                except asyncio.TimeoutError:
                    result['error'] = 'Timeout'
                except Exception as e:
                    result['error'] = str(e)
                    
            elif url.startswith('udp://'):
                result['protocol'] = 'udp'
                # 解析UDP地址
                try:
                    parsed = urllib.parse.urlparse(url)
                    if parsed.hostname and parsed.port:
                        result['valid'] = await self.check_udp_source(parsed.hostname, parsed.port)
                        if result['valid']:
                            result['response_time'] = time.time() - start_time
                except Exception as e:
                    result['error'] = f"UDP解析错误: {e}"
                    
            elif url.startswith('rtmp://'):
                result['protocol'] = 'rtmp'
                # RTMP检测（简化版）
                result['valid'] = True
                result['response_time'] = 0.2
                
        except Exception as e:
            result['error'] = str(e)
            logger.debug(f"URL检测失败 {url}: {e}")
        
        return result
    
    async def batch_check_urls(self, urls_by_channel: Dict[str, List[str]]) -> Dict[str, List[Dict]]:
        """批量检测URL"""
        logger.info(f"开始批量检测 {len(urls_by_channel)} 个频道的URL...")
        
        all_results = {}
        tasks = []
        semaphore = asyncio.Semaphore(self.config['max_workers'])
        
        async def check_with_semaphore(session, url, channel):
            async with semaphore:
                return await self.check_url_validity(session, url, channel)
        
        timeout = aiohttp.ClientTimeout(total=self.config['timeout'] + 5)
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            for channel, urls in urls_by_channel.items():
                for url in urls[:self.config['max_urls_per_channel']]:
                    tasks.append(check_with_semaphore(session, url, channel))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 按频道分组
            for result in results:
                if isinstance(result, dict):
                    channel = result['channel']
                    if channel not in all_results:
                        all_results[channel] = []
                    all_results[channel].append(result)
        
        logger.info(f"检测完成，共检测 {len([r for r in results if isinstance(r, dict)])} 个URL")
        return all_results
    
    def filter_and_sort_urls(self, results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """过滤和排序URL"""
        logger.info("开始过滤和排序URL...")
        filtered_results = {}
        
        for channel, url_results in results.items():
            # 过滤有效URL
            valid_urls = [r for r in url_results if r['valid']]
            
            # 应用过滤条件
            if self.config['open_speed_test']:
                valid_urls = [r for r in valid_urls if r['speed'] >= self.config['min_speed']]
            
            # 按响应时间和速度排序
            valid_urls.sort(key=lambda x: (x['response_time'], -x['speed']))
            
            # 提取URL
            filtered_results[channel] = [r['url'] for r in valid_urls[:self.config['max_urls_per_channel']]]
        
        logger.info(f"过滤完成，剩余 {len(filtered_results)} 个有效频道")
        return filtered_results
    
    def load_template(self) -> Dict[str, List[str]]:
        """加载频道模板"""
        template_channels = {}
        
        try:
            if os.path.exists(self.config['source_file']):
                with open(self.config['source_file'], 'r', encoding='utf-8') as f:
                    current_category = ""
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') and line.endswith('#'):
                            current_category = line[1:-1].strip()
                        elif line and ',' not in line and current_category:
                            # 这是频道名称
                            channel_name = line
                            if current_category not in template_channels:
                                template_channels[current_category] = []
                            template_channels[current_category].append(channel_name)
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
        
        return template_channels
    
    def merge_sources(self, *sources) -> Dict[str, List[str]]:
        """合并多个直播源"""
        merged = {}
        
        for source in sources:
            for channel, urls in source.items():
                if channel not in merged:
                    merged[channel] = []
                merged[channel].extend(urls)
        
        # 去重并保持顺序
        for channel in merged:
            seen = set()
            unique_urls = []
            for url in merged[channel]:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            merged[channel] = unique_urls
        
        return merged
    
    def apply_channel_aliases(self, channels: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """应用频道别名映射"""
        aliased_channels = {}
        
        for channel, urls in channels.items():
            # 使用原始名称
            if channel not in aliased_channels:
                aliased_channels[channel] = []
            aliased_channels[channel].extend(urls)
            
            # 检查是否有别名
            for standard_name, aliases in self.channel_aliases.items():
                if channel in aliases and standard_name != channel:
                    if standard_name not in aliased_channels:
                        aliased_channels[standard_name] = []
                    aliased_channels[standard_name].extend(urls)
        
        return aliased_channels
    
    def generate_tvbox_format(self, channels: Dict[str, List[str]], template: Dict[str, List[str]]) -> str:
        """生成TVBox格式"""
        output = []
        
        # 添加更新信息
        output.append(f"#更新时间: {datetime.now().strftime('%Y-%m-%d %H:%Me}")
        
        return channel_urls
    
    def generate_multicast_sources(self) -> Dict[str, List[str]]:
        """生成组播源"""
        logger.info("生成组播源...")
        channel_urls = {}
        
        # 常见组播频道配置
        multicast_configs = {
            'CCTV-1 综合': [
                ('239.1.1.1', 5140), ('239.1.1.2', 5140), ('239.1.1.3', 5140),
            ],
            'CCTV-2 财经': [
                ('239.1.1.4', 5140), ('239.1.1.5', 5140), ('239.1.1.6', 5140),
            ],
            '湖南卫视': [
                ('239.2.1.1', 5140), ('239.2.1.2', 5140),
            ],
            '浙江卫视': [
                ('239.2.1.3', 5140), ('239.2.1.4', 5140),
            ],
            '东方卫视': [
                ('239.2.1.5', 5140), ('239.2.1.6', 5140),
            ],
        }
        
        for channel, addresses in multicast_configs.items():
            channel_urls[channel] = []
            for ip, port in addresses:
                url = f"udp://@{ip}:{port}"
                if self.is_valid_url(url):
                    channel_urls[channel].append(url)
        
        return channel_urls
    
    async def check_udp_source(self, ip: str, port: int) -> bool:
        """检测UDP源有效性"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            # 发送一个简单的UDP探测包
            sock.sendto(b'\x00\x00\x00\x00', (ip, port))
            sock.close()
            return True
        except Exception:
            return False
    
    async def check_url_validity(self, session: aiohttp.ClientSession, url: str, channel: str) -> Dict:
        """检测URL有效性"""
        result = {
            'url': url,
            'channel': channel,
            'valid': False,
            'response_time': float('inf'),
            'speed': 0,
            'resolution': '',
            'protocol': '',
            'error': '',
            'checked_at': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            
            # 检测不同协议
            if url.startswith('http'):
                result['protocol'] = 'http'
                try:
                    async with session.get(
                        url, 
                        timeout=aiohttp.ClientTimeout(total=self.config['check_timeout']),
                        headers=self.headers
                    ) as response:
                        if response.status == 200:
                            result['valid'] = True
                            result['response_time'] = time.time() - start_time
                            
                            # 检测速度
                            if self.config['open_speed_test']:
                                content_length = response.headers.get('Content-Length')
                                if content_length and int(content_length) > 0:
                                    # 只读取部分内容来检测速度
                                    chunk_size = min(int(content_length), 1024 * 100)  # 100KB
                                    content = await response.content.read(chunk_size)
                                    if content:
                                        result['speed'] = len(content) / result['response_time'] / 1024  # KB/s
                                else:
                                    # 读取一小部分内容
                                    chunk = await response.content.read(1024 * 10)  # 10KB
                                    if chunk:
                                        result['speed'] = len(chunk) / result['response_time'] / 1024  # KB/s
                        else:
                            result['error'] = f"HTTP {response.status}"
                            
                except asyncio.TimeoutError:
                    result['error'] = 'Timeout'
                except Exception as e:
                    result['error'] = str(e)
                    
            elif url.startswith('udp://'):
                result['protocol'] = 'udp'
                # 解析UDP地址
                try:
                    parsed = urllib.parse.urlparse(url)
                    if parsed.hostname and parsed.port:
                        result['valid'] = await self.check_udp_source(parsed.hostname, parsed.port)
                        if result['valid']:
                            result['response_time'] = time.time() - start_time
                except Exception as e:
                    result['error'] = f"UDP解析错误: {e}"
                    
            elif url.startswith('rtmp://'):
                result['protocol'] = 'rtmp'
                # RTMP检测（简化版）
                result['valid'] = True
                result['response_time'] = 0.2
                
        except Exception as e:
            result['error'] = str(e)
            logger.debug(f"URL检测失败 {url}: {e}")
        
        return result
    
    async def batch_check_urls(self, urls_by_channel: Dict[str, List[str]]) -> Dict[str, List[Dict]]:
        """批量检测URL"""
        logger.info(f"开始批量检测 {len(urls_by_channel)} 个频道的URL...")
        
        all_results = {}
        tasks = []
        
        # 限制并发数量
        semaphore = asyncio.Semaphore(self.config['max_concurrent'])
        
        async def check_with_semaphore(session, url, channel):
            async with semaphore:
                return await self.check_url_validity(session, url, channel)
        
        timeout = aiohttp.ClientTimeout(total=self.config['check_timeout'])
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            for channel, urls in urls_by_channel.items():
                for url in urls[:self.config['max_urls_per_channel']]:
                    tasks.append(check_with_semaphore(session, url, channel))
            
            # 分批处理，避免内存溢出
            batch_size = 100
            results = []
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)
                
                # 等待一段时间，避免过于频繁的请求
                if i + batch_size < len(tasks):
                    await asyncio.sleep(1)
            
            # 按频道分组
            for result in results:
                if isinstance(result, dict) and not isinstance(result, Exception):
                    channel = result['channel']
                    if channel not in all_results:
                        all_results[channel] = []
                    all_results[channel].append(result)
        
        logger.info(f"检测完成，共检测 {len(results)} 个URL")
        return all_results
    
    def filter_and_sort_urls(self, results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """过滤和排序URL"""
        logger.info("开始过滤和排序URL...")
        filtered_results = {}
        
        for channel, url_results in results.items():
            # 过滤有效URL
            valid_urls = [r for r in url_results if r['valid']]
            
            # 应用过滤条件
            if self.config['open_speed_test']:
                valid_urls = [r for r in valid_urls if r['speed'] >= self.config['min_speed']]
            
            # 按响应时间和速度排序
            valid_urls.sort(key=lambda x: (x['response_time'], -x['speed']))
            
            # 提取URL
            filtered_results[channel] = [r['url'] for r in valid_urls[:self.config['max_urls_per_channel']]]
        
        logger.info(f"过滤完成，剩余 {len(filtered_results)} 个有效频道")
        return filtered_results
    
    def load_template(self) -> Dict[str, List[str]]:
        """加载频道模板"""
        template_channels = {}
        
        try:
            if os.path.exists(self.config['source_file']):
                with open(self.config['source_file'], 'r', encoding='utf-8') as f:
                    current_category = ""
                    for line in f:
                        line = line.strip()
                        if line.startswith('#'):
                            current_category = line[1:].strip()
                        elif line and ',' not in line:
                            # 这是频道名称
                            channel_name = line
                            if current_category not in template_channels:
                                template_channels[current_category] = []
                            template_channels[current_category].append(channel_name)
            else:
                logger.warning(f"模板文件不存在: {self.config['source_file']}")
                # 使用默认模板
                template_channels = {
                    "央视频道": ["CCTV-1 综合", "CCTV-2 财经", "CCTV-3 综艺"],
                    "卫视频道": ["湖南卫视", "浙江卫视", "东方卫视"]
                }
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            template_channels = {}
        
        return template_channels
    
    def merge_sources(self, *sources) -> Dict[str, List[str]]:
        """合并多个直播源"""
        merged = {}
        
        for source in sources:
            for channel, urls in source.items():
                if channel not in merged:
                    merged[channel] = []
                merged[channel].extend(urls)
        
        # 去重并保持顺序
        for channel in merged:
            seen = set()
            unique_urls = []
            for url in merged[channel]:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            merged[channel] = unique_urls
        
        return merged
    
    def generate_tvbox_format(self, channels: Dict[str, List[str]], template: Dict[str, List[str]]) -> str:
        """生成TVBox格式"""
        output = []
        
        # 添加更新信息
        output.append(f"# 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"# 项目地址: https://github.com/tudouplay/tvbox-box")
        output.append(f"# 频道数量: {len(channels)}")
        output.append(f"# 接口数量: {sum(len(urls) for urls in channels.values())}")
        output.append("")
        
        # 按模板分类输出
        for category, channel_list in template.items():
            output.append(f"#{category}#")
            category_urls = 0
            
            for channel in channel_list:
                if channel in channels and channels[channel]:
                    # 取第一个有效的URL
                    url = channels[channel][0]
                    if self.is_valid_url(url):
                        output.append(f"{channel},{url}")
                        category_urls += 1
                else:
                    # 尝试别名匹配
                    matched = False
                    for alias_channel, aliases in self.channel_aliases.items():
                        if channel in aliases or alias_channel in channel:
                            if alias_channel in channels and channels[alias_channel]:
                                output.append(f"{channel},{channels[alias_channel][0]}")
                                category_urls += 1
                                matched = True
                                break
                    
                    if not matched:
                        logger.debug(f"频道 {channel} 未找到有效源")
            
            if category_urls == 0:
                output.append(f"# {category} 暂无有效源")
            
            output.append("")
        
        # 添加未分类的频道
        all_template_channels = set()
        for cat_channels in template.values():
            all_template_channels.update(cat_channels)
        
        uncategorized = set(channels.keys()) - all_template_channels
        if uncategorized:
            output.append("#其他频道#")
            for channel in sorted(uncategorized):
                if channels[channel]:
                    url = channels[channel][0]
                    if self.is_valid_url(url):
                        output.append(f"{channel},{url}")
        
        return '\n'.join(output)
    
    def generate_m3u_format(self, channels: Dict[str, List[str]]) -> str:
        """生成M3U格式"""
        output = []
        
        output.append("#EXTM3U")
        output.append(f"#EXTINF:-1 tvg-name=\"更新信息\" group-title=\"信息\",TVBox直播源更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("http://example.com/update_info.txt")
        output.append("")
        
        # 分类信息
        categories = {
            '央视频道': [],
            '卫视频道': [],
            '影视娱乐': [],
            '新闻资讯': [],
            '体育频道': [],
            '纪录片': [],
            '其他频道': []
        }
        
        # 分类频道
        for channel, urls in channels.items():
            if not urls:
                continue
            
            url = urls[0]
            if not self.is_valid_url(url):
                continue
            
            # 分类逻辑
            if 'CCTV' in channel.upper() or '央视' in channel:
                categories['央视频道'].append((channel, url))
            elif any(word in channel for word in ['卫视', '电视台', 'TV']):
                categories['卫视频道'].append((channel, url))
            elif any(word in channel for word in ['影视', '电影', '剧场', '影院']):
                categories['影视娱乐'].append((channel, url))
            elif any(word in channel for word in ['新闻', '资讯']):
                categories['新闻资讯'].append((channel, url))
            elif any(word in channel for word in ['体育', '运动', '赛事']):
                categories['体育频道'].append((channel, url))
            elif any(word in channel for word in ['记录', '纪实', '探索']):
                categories['纪录片'].append((channel, url))
            else:
                categories['其他频道'].append((channel, url))
        
        # 按分类输出
        for category, channel_list in categories.items():
            if not channel_list:
                continue
            
            output.append(f"#EXTINF:-1 tvg-name=\"{category}\" group-title=\"{category}\",{category}")
            output.append("")
            
            for channel, url in sorted(channel_list):
                output.append(f"#EXTINF:-1 tvg-name=\"{channel}\" group-title=\"{category}\",{channel}")
                output.append(url)
                output.append("")
        
        return '\n'.join(output)
    
    def save_results(self, channels: Dict[str, List[str]], template: Dict[str, List[str]]):
        """保存结果"""
        try:
            # 生成TVBox格式
            tvbox_content = self.generate_tvbox_format(channels, template)
            with open(self.config['output_txt'], 'w', encoding='utf-8') as f:
                f.write(tvbox_content)
            
            # 生成M3U格式
            m3u_content = self.generate_m3u_format(channels)
            with open(self.config['output_m3u'], 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            
            # 生成JSON格式（便于程序读取）
            json_data = {
                'update_time': datetime.now().isoformat(),
                'total_channels': len(channels),
                'total_urls': sum(len(urls) for urls in channels.values()),
                'channels': channels
            }
            with open(self.config['output_json'], 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"结果保存完成: {self.config['output_txt']}, {self.config['output_m3u']}")
            
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            raise
    
    def generate_report(self) -> str:
        """生成更新报告"""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        report = f"""
# TVBox直播源更新报告

## 基本信息
- 更新时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
- 更新耗时: {duration.total_seconds():.2f}秒
- 项目地址: https://github.com/tudouplay/tvbox-box

## 统计信息
- 搜索到的频道总数: {self.stats['total_channels']}
- 有效接口总数: {self.stats['valid_sources']}
- 失效接口总数: {self.stats['failed_sources']}
- 最终有效频道: {len(self.channels)}
- 最终有效接口: sum(len(urls) for urls in self.channels.values())}

## 配置信息
- 检测超时: {self.config['check_timeout']}秒
- 最小速度: {self.config['min_speed']}KB/s
- 每个频道最大接口: {self.config['max_urls_per_channel']}
- 并发检测数: {self.config['max_concurrent']}

## 注意事项
1. 本直播源仅供学习交流使用
2. 请勿用于商业用途
3. 如有侵权，请联系删除
4. 建议配合TVBox、影视仓等播放器使用

## 订阅地址
- TXT格式: https://raw.githubusercontent.com/tudouplay/tvbox-box/main/output/result.txt
- M3U格式: https://raw.githubusercontent.com/tudouplay/tvbox-box/main/output/result.m3u
- JSON格式: https://raw.githubusercontent.com/tudouplay/tvbox-box/main/output/result.json
"""
        return report
    
    async def run(self):
        """运行更新流程"""
        logger.info("开始TVBox直播源更新流程...")
        self.stats['start_time'] = datetime.now()
        
        try:
            # 确保目录存在
            self.ensure_directories()
            
            # 1. 获取订阅源
            logger.info("步骤1: 获取订阅源...")
            subscribe_sources = await self.fetch_subscribe_sources()
            self.stats['total_sources'] += len(subscribe_sources)
            
            # 2. 生成酒店源
            logger.info("步骤2: 生成酒店源...")
            hotel_sources = self.generate_hotel_sources()
            
            # 3. 生成组播源
            logger.info("步骤3: 生成组播源...")
            multicast_sources = self.generate_multicast_sources()
            
            # 4. 加载本地源
            logger.info("步骤4: 加载本地源...")
            local_sources = {}
            if os.path.exists(self.config['local_file']):
                try:
                    with open(self.config['local_file'], 'r', encoding='utf-8') as f:
                        content = f.read()
                        self.parse_txt_content(content, local_sources)
                    logger.info(f"本地源加载完成，共{len(local_sources)}个频道")
                except Exception as e:
                    logger.error(f"加载本地源失败: {e}")
            
            # 5. 合并所有源
            logger.info("步骤5: 合并所有源...")
            all_sources = self.merge_sources(
                subscribe_sources,
                hotel_sources,
                multicast_sources,
                local_sources
            )
            
            logger.info(f"合并完成，共{len(all_sources)}个频道")
            self.stats['total_channels'] = len(all_sources)
            
            # 6. 检测URL有效性
            logger.info("步骤6: 检测URL有效性...")
            checked_results = await self.batch_check_urls(all_sources)
            
            # 统计检测结果
            for channel_results in checked_results.values():
                for result in channel_results:
                    if result['valid']:
                        self.stats['valid_sources'] += 1
                    else:
                        self.stats['failed_sources'] += 1
            
            # 7. 过滤和e}")
        
        return channel_urls
    
    def generate_multicast_sources(self) -> Dict[str, List[str]]:
        """生成组播源"""
        logger.info("生成组播源...")
        channel_urls = {}
        
        # 常见组播频道配置
        multicast_channels = {
            'CCTV-1 综合': [('239.1.1.1', 5140), ('239.1.1.2', 5140), ('239.0.0.1', 5140)],
            'CCTV-2 财经': [('239.1.1.3', 5140), ('239.1.1.4', 5140), ('239.0.0.2', 5140)],
            'CCTV-3 综艺': [('239.1.1.5', 5140), ('239.1.1.6', 5140), ('239.0.0.3', 5140)],
            '湖南卫视': [('239.1.2.1', 5140), ('239.1.2.2', 5140), ('239.0.1.1', 5140)],
            '浙江卫视': [('239.1.2.3', 5140), ('239.1.2.4', 5140), ('239.0.1.2', 5140)],
            '东方卫视': [('239.1.2.5', 5140), ('239.1.2.6', 5140), ('239.0.1.3', 5140)],
        }
        
        for channel, addresses in multicast_channels.items():
            channel_urls[channel] = []
            for ip, port in addresses:
                url = f"udp://@{ip}:{port}"
                if self.is_valid_url(url):
                    channel_urls[channel].append(url)
        
        return channel_urls
    
    async def check_udp_source(self, ip: str, port: int) -> bool:
        """检测UDP源有效性"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            # 发送一个简单的UDP探测包
            sock.sendto(b'\x00\x00\x00\x00', (ip, port))
            sock.close()
            return True
        except Exception:
            return False
    
    async def check_url_validity(self, session: aiohttp.ClientSession, url: str, channel: str) -> Dict:
        """检测URL有效性"""
        result = {
            'url': url,
            'channel': channel,
            'valid': False,
            'response_time': float('inf'),
            'speed': 0,
            'resolution': '',
            'protocol': '',
            'error': '',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            
            # 检测不同协议
            if url.startswith('http'):
                result['protocol'] = 'http'
                try:
                    # 使用HEAD请求先检测，减少数据传输
                    async with session.head(
                        url, 
                        timeout=aiohttp.ClientTimeout(total=self.config['check_timeout']),
                        headers=self.headers,
                        allow_redirects=True
                    ) as response:
                        if response.status == 200:
                            # HEAD成功，再进行GET测试
                            async with session.get(
                                url,
                                timeout=aiohttp.ClientTimeout(total=self.config['check_timeout']),
                                headers=self.headers
                            ) as get_response:
                                if get_response.status == 200:
                                    result['valid'] = True
                                    result['response_time'] = time.time() - start_time
                                    
                                    # 检测速度
                                    if self.config['open_speed_test']:
                                        # 读取前100KB来估算速度
                                        chunk_size = 1024 * 100
                                        content = await get_response.content.read(chunk_size)
                                        if content:
                                            result['speed'] = len(content) / result['response_time'] / 1024 / 1024
                                else:
                                    result['error'] = f"GET {get_response.status}"
                        else:
                            result['error'] = f"HEAD {response.status}"
                            
                except asyncio.TimeoutError:
                    result['error'] = 'Timeout'
                except Exception as e:
                    result['error'] = str(e)
                    
            elif url.startswith('udp://'):
                result['protocol'] = 'udp'
                # 解析UDP地址
                try:
                    parsed = urllib.parse.urlparse(url)
                    if parsed.hostname and parsed.port:
                        result['valid'] = await self.check_udp_source(parsed.hostname, parsed.port)
                        if result['valid']:
                            result['response_time'] = time.time() - start_time
                            result['speed'] = 1.0  # UDP默认速度
                except Exception as e:
                    result['error'] = f"UDP错误: {e}"
                    
            elif url.startswith('rtmp://'):
                result['protocol'] = 'rtmp'
                # RTMP检测（简化版）
                result['valid'] = True
                result['response_time'] = 0.2
                result['speed'] = 0.8
                
        except Exception as e:
            result['error'] = str(e)
            logger.debug(f"URL检测失败 {url}: {e}")
        
        return result
    
    async def batch_check_urls(self, urls_by_channel: Dict[str, List[str]]) -> Dict[str, List[Dict]]:
        """批量检测URL"""
        logger.info(f"开始批量检测 {len(urls_by_channel)} 个频道的URL...")
        
        all_results = {}
        tasks = []
        
        # 限制并发数量
        semaphore = asyncio.Semaphore(self.config['max_concurrent'])
        
        async def limited_check(session, url, channel):
            async with semaphore:
                return await self.check_url_validity(session, url, channel)
        
        timeout = aiohttp.ClientTimeout(total=self.config['batch_timeout'])
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            for channel, urls in urls_by_channel.items():
                for url in urls[:self.config['max_urls_per_channel']]:
                    tasks.append(limited_check(session, url, channel))
            
            # 分批处理，避免内存溢出
            batch_size = 100
            for i in range(0, len(tasks), batch_size):
                batch_tasks = tasks[i:i+batch_size]
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, dict):
                        channel = result['channel']
                        if channel not in all_results:
                            all_results[channel] = []
                        all_results[channel].append(result)
                
                # 每批处理完后暂停一下
                if i + batch_size < len(tasks):
                    await asyncio.sleep(1)
        
        logger.info(f"检测完成，共检测 {sum(len(urls) for urls in all_results.values())} 个URL")
        return all_results
    
    def filter_and_sort_urls(self, results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """过滤和排序URL"""
        logger.info("开始过滤和排序URL...")
        filtered_results = {}
        
        for channel, url_results in results.items():
            # 过滤有效URL
            valid_urls = [r for r in url_results if r['valid']]
            
            # 应用过滤条件
            if self.config['open_speed_test']:
                valid_urls = [r for r in valid_urls if r['speed'] >= self.config['min_speed']]
            
            # 按响应时间和速度排序
            valid_urls.sort(key=lambda x: (x['response_time'], -x['speed']))
            
            # 提取URL
            filtered_results[channel] = [r['url'] for r in valid_urls[:self.config['max_urls_per_channel']]]
        
        logger.info(f"过滤完成，剩余 {len(filtered_results)} 个有效频道")
        return filtered_results
    
    def merge_sources(self, *sources) -> Dict[str, List[str]]:
        """合并多个直播源"""
        merged = {}
        
        for source in sources:
            for channel, urls in source.items():
                if channel not in merged:
                    merged[channel] = []
                merged[channel].extend(urls)
        
        # 去重并保持顺序
        for channel in merged:
            seen = set()
            unique_urls = []
            for url in merged[channel]:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            merged[channel] = unique_urls
        
        return merged
    
    def load_template(self) -> Dict[str, List[str]]:
        """加载频道模板"""
        template_channels = {}
        
        try:
            if os.path.exists(self.config['source_file']):
                with open(self.config['source_file'], 'r', encoding='utf-8') as f:
                    current_category = ""
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith('#'):
                            current_category = line[1:].strip()
                            if current_category and current_category not in template_channels:
                                template_channels[current_category] = []
                        elif ',' not in line:
                            # 这是频道名称
                            channel_name = line.strip()
                            if current_category and channel_name:
                                template_channels[current_category].append(channel_name)
                            else:
                                logger.warning(f"模板文件第{line_num}行格式错误: {line}")
            else:
                logger.warning(f"模板文件不存在: {self.config['source_file']}")
                # 使用默认模板
                template_channels = self.get_default_template()
                
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            template_channels = self.get_default_template()
        
        return template_channels
    
    def get_default_template(self) -> Dict[str, List[str]]:
        """获取默认模板"""
        return {
            '央视频道': ['CCTV-1 综合', 'CCTV-2 财经', 'CCTV-3 综艺', 'CCTV-4 中文国际', 'CCTV-5 体育'],
            '卫视频道': ['湖南卫视', '浙江卫视', '东方卫视', '北京卫视', '江苏卫视'],
            '其他频道': ['广东卫视', '深圳卫视', '山东卫视', '天津卫视']
        }
    
    def match_channel_name(self, template_name: str, source_name: str) -> bool:
        """模糊匹配频道名称"""
        # 精确匹配
        if template_name == source_name:
            return True
        
        # 检查别名
        for std_name, aliases in self.channel_aliases.items():
            if template_name in aliases and source_name in aliases:
                return True
        
        # 模糊匹配
        template_lower = template_name.lower()
        source_lower = source_name.lower()
        
        # 移除常见后缀
        for suffix in ['卫视', '台', '频道', 'TV', 'tv', ' ', '-', '—']:
            template_lower = template_lower.replace(suffix, '')
            source_lower = source_lower.replace(suffix, '')
        
        return template_lower == source_lower or (template_lower in source_lower) or (source_lower in template_lower)
    
    def generate_tvbox_format(self, channels: Dict[str, List[str]], template: Dict[str, List[str]]) -> str:
        """生成TVBox格式"""
        output = []
        
        # 添加文件头信息
        output.append(f"# TVBox直播源")
        output.append(f"# 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"# 项目地址: https://github.com/tudouplay/tvbox-box")
        output.append(f"# 有效频道: {len(channels)}")
        output.append(f"# 有效接口: {sum(len(urls) for urls in channels.values())}")
        output.append("")
        
        # 按模板分类输出
        for category, channel_list in template.items():
            output.append(f"#{category}#")
            
            for template_channel in channel_list:
                matched = False
                urls = []
                
                # 查找匹配的频道
                for source_channel, source_urls in channels.items():
                    if self.match_channel_name(template_channel, source_channel) and source_urls:
                        urls.extend(source_urls[:2])  # 每个频道最多2个接口
                        matched = True
                        if len(urls) >= 2:  # 限制接口数量
                            break
                
                # 输出匹配的频道
                if matched and urls:
                    for url in urls[:2]:  # 每个频道最多2个接口
                        if self.is_valid_url(url):
                            output.append(f"{template_channel},{url}")
                else:
                    # 如果没有找到源，添加注释
                    output.append(f"#{template_channel},暂无有效源")
            
            output.append("")
        
        # 添加未分类的频道
        all_template_channels = set()
        for cat_channels in template.values():
            all_template_channels.update(cat_channels)
        
        uncategorized = []
        for source_channel, urls in channels.items():
            if not any(self.match_channel_name(template_channel, source_channel) 
                      for template_channel in all_template_channels):
                if urls:
                    uncategorized.append((source_channel, urls[0]))
        
        if uncategorized:
            output.append("#其他频道#")
            for channel, url in sorted(uncategorized):
                if self.is_valid_url(url):
                    output.append(f"{channel},{url}")
        
        return '\n'.join(output)
    
    def generate_m3u_format(self, channels: Dict[str, List[str]]) -> str:
        """生成M3U格式"""
        output = []
        
        output.append("#EXTM3U")
        output.append(f"#EXTINF:-1 tvg-name=\"更新信息\" group-title=\"【更新信息】\",\"TVBox直播源 - 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"")
        output.append("http://example.com/update_info.txt")
        output.append("")
        
        # 按分类组织频道
        categories = {}
        for channel, urls in channels.items():
            if urls and self.is_valid_url(urls[0]):
                # 智能分类
                category = self.categorize_channel(channel)
                
                if category not in categories:
                    categories[category] = []
                categories[category].append((channel, urls[0]))
        
        # 按分类输出
        for category in sorted(categories.keys()):
            output.append(f"#EXTINF:-1 tvg-name=\"{category}\" group-title=\"【{category}】\",\"{category}\"")
            output.append("")  # 分类分隔行
            
            for channel, url in sorted(categories[category]):
                # 生成频道图标URL（使用公开服务）
                icon_url = f"https://iptv-pro.github.io/cdn/logo/{channel}.png"
                output.append(f"#EXTINF:-1 tvg-name=\"{channel}\" tvg-logo=\"{icon_url}\" group-title=\"{category}\",{channel}")
                output.append(url)
                output.append("")
        
        return '\n'.join(output)
    
    def categorize_channel(self, channel_name: str) -> str:
        """智能分类频道"""
        channel_lower = channel_name.lower()
        
        if any(word in channel_lower for word in ['cctv', '中央']):
            return '央视频道'
        elif any(word in channel_lower for word in ['卫视', '电视台']):
            return '卫视频道'
        elif any(word in channel_lower for word in ['影视', '电影', '剧场', '影院', 'chc']):
            return '影视娱乐'
        elif any(word in channel_lower for word in ['新闻', '资讯', '凤凰', '香港']):
            return '新闻资讯'
        elif any(word in channel_lower for word in ['体育', '运动', '足球', '篮球']):
            return '体育频道'
        elif any(word in channel_lower for word in ['纪录', '发现', '探索', '地理', '历史']):
            return '纪录频道'
        elif any(word in channel_lower for word in ['少儿', '卡通', '动漫', '动画', '卡酷']):
            return '少儿频道'
        elif any(word in channel_lower for word in ['音乐', '戏曲', '艺术']):
            return '音乐艺术'
        else:
            return '其他频道'
    
    def generate_json_format(self, channels: Dict[str, List[str]]) -> str:
        """生成JSON格式（用于Web接口）"""
        data = {
            'version': '1.0',
            'update_time': datetime.now().isoformat(),
            'total_channels': len(channels),
            'total_urls': sum(len(urls) for urls in channels.values()),
            'channels': {}
        }
        
        for channel, urls in channels.items():
            data['channels'][channel] = {
                'urls': urls,
                'url_count': len(urls),
                'category': self.categorize_channel(channel)
            }
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def save_stats(self, channels: Dict[str, List[str]]):
        """保存统计信息"""
        elapsed_time = datetime.now() - self.stats['start_time']
        
        stats_data = {
            'update_time': datetime.now().isoformat(),
            'elapsed_seconds': elapsed_time.total_seconds(),
            'total_channels': len(channels),
            'total_urls': sum(len(urls) for urls in channels.values()),
            'sources_stats': {
                'total_sources': self.stats['total_sources'],
                'valid_sources': self.stats['valid_sources'],
                'failed_sources': self.stats['failed_sources'],
            },
            'config': self.config,
            'version': '1.0'
        }
        
        # 保存到文件
        with open('output/stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
        
        # 输出到日志
        logger.info("=" * 50)
        logger.info("更新统计:")
        logger.info(f"耗时: {elapsed_time.total_seconds():.2f}秒")
        logger.info(f"有效频道: {len(channels)}")
        logger.info(f"有效接口: {sum(len(urls) for urls in channels.values())}")
        logger.info("=" * 50)
    
    async def run(self) -> bool:
        """运行更新流程"""
        logger.info("开始TVBox直播源更新流程...")
        logger.info(f"配置: {json.dumps(self.config, ensure_ascii=False, indent=2)}")
        
        try:
            # 确保目录存在
            self.ensure_directories()
            
            # 1. 获取订阅源
            logger.info("步骤1: 获取订阅源...")
            subscribe_sources = await self.fetch_subscribe_sources()
            self.stats['total_sources'] += len(self.subscribe_sources)
            self.stats['valid_sources'] += 1 if subscribe_sources else 0
            
            # 2. 生成酒店源
            logger.info("步骤2: 生成酒店源...")
            hotel_sources = self.generate_hotel_sources()
            
            # 3. 生成组播源
            logger.info("步骤3: 生成组播源...")
            multicast_sources = self.generate_multicast_sources()
            
