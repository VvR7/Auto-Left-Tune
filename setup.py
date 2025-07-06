from huggingface_hub import hf_hub_download
import shutil
import os

# 仓库信息
repo_id = "jerryzhou2/ALT_transformer"
filename = "model1.pt"

# 下载到 huggingface 缓存路径
downloaded_path = hf_hub_download(repo_id=repo_id, filename=filename)

# 你想保存的本地目标路径
#当前脚本所在路径
abs_path = os.path.abspath(__file__)
abs_path = os.path.dirname(abs_path)
os.makedirs(os.path.join(abs_path,'app','utils','model'),exist_ok=True)
target_path = os.path.join(abs_path,'app','utils','model',filename)
print(target_path)

# 拷贝到目标路径
shutil.copy(downloaded_path, target_path)
# 确保目标目录存在
print(f"模型已保存到: {target_path}")