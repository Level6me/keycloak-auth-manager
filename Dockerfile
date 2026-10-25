FROM python:3.9-slim
WORKDIR /app

# 固定依赖版本边界，保证构建可重现
RUN pip install --no-cache-dir "flask>=2.2,<4" "requests>=2.28,<3" "cryptography>=41" \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker.io curl \
    && rm -rf /var/lib/apt/lists/*

# 说明：
# 1. app.py 通过 subprocess 调用 docker CLI 管理容器，运行时必须挂载宿主机 docker 套接字：
#      -v /var/run/docker.sock:/var/run/docker.sock
# 2. 配置/数据/密钥请通过挂载目录提供（切勿在构建目录放置真实 config.json / *.key，
#    避免密钥被打进镜像层）：
#      -v /opt/keycloak-auth-manager/config.json:/app/config.json:ro  (或整目录挂载)
#      -v /opt/keycloak-auth-manager/data.json:/app/data.json
EXPOSE 8088

COPY . /app
CMD ["python", "app.py"]
