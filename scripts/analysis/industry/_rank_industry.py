"""处理 ths_daily 数据，提取行业排名并映射名称"""
import json

# 先通过 ths_index 获取名称映射
data_raw = ""  # 上方MCP返回的JSON数据，这里简化处理

# 数据已在上一轮获取，直接用 Python 排序
# 先保存为文件便于处理
