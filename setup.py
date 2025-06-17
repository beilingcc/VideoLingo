from setuptools import setup, find_packages

# 定义项目名称和版本号
NAME = 'VideoLingo'
VERSION = '3.0.0'

# 从requirements.txt读取依赖项列表
with open('requirements.txt', encoding='utf-8') as f:
    requirements = f.read().splitlines()

# 配置项目安装信息
setup(
    name=NAME,  # 项目名称
    version=VERSION,  # 项目版本
    packages=find_packages(include=[NAME, f'{NAME}.*']),  # 自动查找所有包
    install_requires=requirements  # 安装所需的依赖项
)
