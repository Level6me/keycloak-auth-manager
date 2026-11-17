FROM python:3.9-slim
WORKDIR /app

# 固定依赖版本边界，保证构建可重现
RUN pip install --no-cache-dir "flask>=2.2,<4" "requests>=2.28,<3" "waitress>=2.0,<3" "cryptography>=41" \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker.io curl \
    && rm -rf /var/lib/apt/lists/*

# 说明：
# 1. app.py 通过 subprocess 调用 docker CLI 管理容器，运行时必须挂载宿主机 docker 套接字：
#      -v /var/run/docker.sock:/var/run/docker.sock
# 2. 配置、数据与密钥使用应用实际读取的绝对路径挂载（切勿将真实密钥打进镜像层）：
#      -v /opt/keycloak-auth-manager:/opt/keycloak-auth-manager
# 3. 完整管理 1Panel OpenResty 还需挂载宿主机对应目录，并使用 host 网络；独立容器部署
#    若未提供这些宿主机资源，不支持自动创建网站或修改其 Nginx 配置。
EXPOSE 8088

COPY . /app
CMD ["python", "app.py"]
