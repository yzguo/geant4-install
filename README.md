# Geant4-install

Geant4 在 Linux 及 Docker 中的安装脚本

## 在物理机/虚拟机 (Debian/Ubuntu) 中安装

需要有 sudo 权限或以 root 用户执行如下命令：

```bash
wget https://github.com/yzguo/geant4-install | sh
```

该脚本会将 Geant4 安装到 $HOME/geant4/ 目录中。

## 在 Docker 中安装

需要有 sudo 权限或以 root 用户执行如下命令：

```bash
git clone https://github.com/yzguo/geant4-install.git
cd geant4-v11.3.2-docker/
make build
make run
```

然后就可以使用用浏览器访问 127.0.0.1:8080 来使用 Geant4 了，也可以在局域网中通过将 127.0.0.1 替换为主机的 IP 地址来访问。
