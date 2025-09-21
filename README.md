# TVBox 国际电视频道直播源接口

这是一个为TVBox提供国际电视频道直播源的接口服务，具备自动搜索、更新和替换无效直播源的功能。

## 功能特点

- 自动从多个来源获取国际电视频道直播源
- 定期检查并更新无效的直播源
- 支持按国家、分类、语言筛选频道
- 提供RESTful API接口供TVBox客户端使用
- 自动去重，确保直播源唯一性

## 安装与使用

### 环境要求

- Python 3.6+
- pip

### 安装步骤

1. 克隆仓库git clone https://github.com/tudouplay/tvbox-box.git
cd tvbox-box
2. 安装依赖pip install -r requirements.txt
3. 启动服务python app.py
服务将在本地5000端口启动，可通过http://localhost:5000访问

## API 接口说明

### 获取所有频道GET /api/channels可选参数:
- country: 按国家筛选
- category: 按分类筛选
- language: 按语言筛选
- search: 搜索频道名称

### 获取单个频道GET /api/channel/<channel_id>
### 手动更新直播源POST /api/update
### 手动检查无效源POST /api/check
### 获取国家列表GET /api/countries
### 获取分类列表GET /api/categories
### 获取语言列表GET /api/languages
## 自动更新机制

服务会每小时自动执行以下操作:
1. 从配置的仓库更新直播源
2. 检查现有直播源的有效性
3. 为无效的直播源寻找替代源

## 自定义配置

你可以修改`app.py`中的以下参数进行自定义:
- `BACKUP_REPOSITORIES`: 直播源仓库列表
- `MAX_WORKERS`: 并发检查的线程数
- `TIMEOUT`: 直播源检查超时时间
- `CHECK_INTERVAL`: 自动检查间隔(秒)
