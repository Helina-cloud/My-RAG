# My-RAG

在浏览器里搭建**本地知识库问答**：把文档变成可检索的向量库，用 **DeepSeek** 根据文档内容回答问题。界面基于 **Streamlit**，开箱即用。

---

## 能做什么

- **对话问答**：在页面下方输入问题，系统会从你的文档里检索相关内容再生成回答。
- **上传文档**：在左侧边栏上传 `.txt` / `.md`，一键写入知识库（向量库）。
- **全量重建**：若你改动了磁盘上的文档或想清空重来，可勾选「重建向量库」再入库（会删除旧向量库后重新构建）。

---

## 使用前准备

1. 已安装 **Python 3.10+**（推荐 3.11/3.12）。
2. 拥有 **DeepSeek API Key**（用于对话与默认的向量 embedding）。

---

## 安装与启动

在项目目录下执行：

```bash
python -m venv .venv
```

**Windows（PowerShell）：**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux：**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 配置 API Key

1. 复制一份环境变量模板（若仓库中有 `.env.example`）为 **`.env`**，放在项目根目录。
2. 至少填写：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | 你在 DeepSeek 控制台申请的密钥（必填） |

可选（一般保持默认即可）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 对话模型 |
| `DEEPSEEK_EMBEDDING_MODEL` | 与下方 `RAG_EMBEDDING_MODEL` 配合 | 向量模型名，以官方文档为准 |

应用启动时会自动读取项目根目录下的 **`.env`** 和 **`api.env`**（二者择一或同时存在均可，注意不要把密钥提交到公开仓库）。

---

## 启动网页

```bash
streamlit run streamlit_app.py
```

浏览器打开终端里提示的地址（一般为 `http://localhost:8501`）。

---

## 部署到 Streamlit Cloud（密钥怎么配）

云端**没有**你电脑上的 `.env` 文件，也不能把真实 Key 写进代码或提交到 Git。请用 **Streamlit Secrets**：

1. 打开 [share.streamlit.io](https://share.streamlit.io) 里你的应用 → **Settings（齿轮）** → **Secrets**。
2. 在编辑器里粘贴 **TOML**，至少包含 `DEEPSEEK_API_KEY`，例如：

```toml
DEEPSEEK_API_KEY = "sk-你的密钥"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_EMBEDDING_MODEL = "deepseek-embedding"
RAG_EMBEDDING_PROVIDER = "deepseek"
```

3. 点击 **Save**，等待应用重新部署（或点 **Reboot app**）。

应用启动时会从 `st.secrets` **同步到环境变量**，供对话和向量入库使用（与本地读 `.env` 行为一致）。

**注意**：Streamlit Cloud 的文件系统是**临时的**，容器重启后本机上的 `docs/`、`chroma_db/` 可能清空。若只在网页里上传文档，重启后需重新上传并入库；需要长期保留可考虑外挂存储（S3 等），属进阶配置。

---

## 在网页里怎么用

1. **先建知识库（二选一）**  
   - **方式 A**：把 `.txt` / `.md` 文件放进项目下的 **`docs/`** 文件夹，首次对话或首次入库时会自动用这些文件建库（若向量库为空）。  
   - **方式 B**：在左侧 **「知识库管理」** 里上传文件，点击 **「入库」**。文件会保存到 `docs/`，并写入向量库。

2. **需要「从零重建」时**  
   勾选 **「重建向量库（会清空旧库）」**，再点 **「入库」**。适合换了一批文档、或发现检索结果异常时。

3. **开始提问**  
   在页面下方输入框用自然语言提问即可。支持多轮对话；回答会尽量依据已入库的文档内容。

---

## 文件与目录说明（用户可见结果）

| 路径 | 作用 |
|------|------|
| `docs/` | 存放知识文档（上传的文件也会保存在这里） |
| `chroma_db/` | 向量数据库（自动生成，可删除后通过「重建」再生成） |

---

## 常见问题

**打不开页面或提示缺少 Key**  
- **本地**：检查 `.env` 或 `api.env` 里是否填写 `DEEPSEEK_API_KEY`。  
- **Streamlit Cloud**：在应用 **Settings → Secrets** 里配置（见上文「部署到 Streamlit Cloud」），保存并等待重新部署。

**回答与我的文档无关**  
确认已完成「入库」或 `docs/` 里已有内容；必要时勾选「重建向量库」再入库一次。

**Embedding 报错**  
默认使用 DeepSeek 的向量接口；若官方模型名称有变更，请在环境变量中调整 `DEEPSEEK_EMBEDDING_MODEL` / `RAG_EMBEDDING_MODEL`，并查阅 DeepSeek 最新文档。

**只想用本地向量模型、不调用云端 Embedding**  
可将 `RAG_EMBEDDING_PROVIDER` 设为 `hf`，并配置对应的 `RAG_EMBEDDING_MODEL`（需安装 `sentence-transformers` 等依赖，首次运行会下载模型，体积较大）。

**报错：`Descriptors cannot be created directly`（protobuf）**  
多半是 **`protobuf` 4.x 与部分依赖里旧版生成的 `_pb2.py` 不兼容**。本项目已在 `requirements.txt` 中限制 `protobuf>=3.20,<4`；请在当前环境重新安装依赖，例如：

```bash
pip install -r requirements.txt
```

若仍报错，可再尝试在运行前设置环境变量：`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`（会变慢，一般仅作临时兜底）。

---

## 当前限制

- 支持的文档格式：**`.txt`**、**`.md`**。PDF、Word 等需自行先转为文本或后续扩展功能。
- 知识库与向量库均保存在本机目录，换电脑需拷贝 `docs/` 与 `chroma_db/`（或在新环境重新上传/重建）。
