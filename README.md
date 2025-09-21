#!/bin/bash
# 一键部署TVBox直播源管理系统

echo "🚀 开始部署TVBox直播源管理系统..."

# 创建目录结构
mkdir -p tvbox-box/{config,output,.github/workflows}

# 下载所有文件
echo "📥 下载配置文件..."

# GitHub Actions配置
cat > tvbox-box/.github/workflows/update.yml << 'EOF'
name: 自动更新TVBox直播源

on:
  schedule:
    - cron: '0 6,18 * * *'  # 每天6点和18点更新
  workflow_dispatch:        # 支持手动触发

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    
    steps:
    - name: 检出代码
      uses: actions/checkout@v4
      
    - name: 设置Python环境
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
        
    - name: 安装依赖
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        
    - name: 运行更新脚本
      run: python main.py
      
    - name: 提交更新结果
      run: |
        git config --local user.email "action@github.com"
        git config --local user.name "GitHub Action"
        git add output/
        git diff --quiet && git diff --staged --quiet || git commit -m "自动更新TVBox直播源 - $(date +'%Y-%m-%d %H:%M:%S')"
        git push
EOF

# 频道模板
cat > tvbox-box/config/demo.txt << 'EOF'
#央视频道
CCTV-1 综合
CCTV-2 财经
CCTV-3 综艺
CCTV-4 中文国际
CCTV-5 体育
CCTV-5+ 体育赛事
CCTV-6 电影
CCTV-7 国防军事
CCTV-8 电视剧
CCTV-9 纪录
CCTV-10 科教
CCTV-11 戏曲
CCTV-12 社会与法
CCTV-13 新闻
CCTV-14 少儿
CCTV-15 音乐
CCTV-16 奥林匹克
CCTV-17 农业农村

#卫视频道
湖南卫视
浙江卫视
东方卫视
北京卫视
江苏卫视
广东卫视
深圳卫视
山东卫视
天津卫视
重庆卫视
安徽卫视
四川卫视
湖北卫视
江西卫视
辽宁卫视
黑龙江卫视
河北卫视
河南卫视
广西卫视
福建东南卫视
贵州卫视
云南卫视
旅游卫视
吉林卫视
山西卫视
陕西卫视
甘肃卫视
青海卫视
宁夏卫视
内蒙古卫视
新疆卫视
西藏卫视

#影视娱乐
CHC高清电影
CHC动作电影
CHC家庭影院
欢笑剧场
都市剧场
劲爆体育
快乐垂钓
茶频道
嘉佳卡通
优漫卡通
金鹰卡通
炫动卡通
卡酷少儿

#新闻资讯
中国新闻
北京新闻
上海新闻
广东新闻
深圳新闻
凤凰中文台
凤凰资讯台
凤凰香港台
香港卫视
阳光卫视
星空卫视
华娱卫视

#体育频道
CCTV风云足球
CCTV高尔夫网球
体育赛事
北京体育
广东体育
上海体育
劲爆体育
快乐垂钓
四海钓鱼

#纪录片
CCTV世界地理
CCTV发现之旅
CCTV老故事
CCTV第一剧场
CCTV怀旧剧场
CCTV兵器科技
CCTV文化精品
CCTV央视台球
CCTV卫生健康
EOF

# requirements.txt
cat > tvbox-box/requirements.txt << 'EOF'
aiohttp>=3.8.0,<4.0.0
requests>=2.28.0
asyncio>=3.4.3
beautifulsoup4>=4.11.0
tqdm>=4.64.0
lxml>=4.9.0
EOF

# Dockerfile
cat > tvbox-box/Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY main.py .
COPY config/ ./config/
COPY output/ ./output/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建必要的目录
RUN mkdir -p /app/output /app/config

# 设置时区
ENV TZ=Asia/Shanghai

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 运行脚本
CMD ["python", "main.py"]
EOF

echo "✅ 配置文件创建完成！"
echo "📁 项目目录: tvbox-box/"
echo ""
echo "下一步:"
echo "1. cd tvbox-box"
echo "2. 下载main.py文件"
echo "3. 运行: python main.py"
