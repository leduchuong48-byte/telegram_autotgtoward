ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# 设置工作目录
WORKDIR /app

# 设置Docker日志配置
ENV DOCKER_LOG_MAX_SIZE=10m
ENV DOCKER_LOG_MAX_FILE=3

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    ca-certificates \
    gcc \
    python3-dev \
    && ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 --timeout 120 \
    -i "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    -r requirements.txt

# 创建临时文件目录
RUN mkdir -p /app/temp

# 复制应用代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["python", "main.py"]
