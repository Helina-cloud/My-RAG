import os
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from langchain_core.documents import Document

from rag_store import add_docs_to_chroma, from_env, load_or_create_chroma, rebuild_chroma_from_docs


def _sync_streamlit_secrets_to_env() -> None:
    """Streamlit Cloud 只在 st.secrets 里注入密钥；rag_store 等模块读的是 os.environ，这里做一次同步。"""
    try:
        sec = st.secrets
        pairs = sec.items() if hasattr(sec, "items") else ((k, sec[k]) for k in sec)
        for k, v in pairs:
            if isinstance(v, dict):
                continue
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            key = str(k)
            if not os.getenv(key):
                os.environ[key] = str(v)
    except Exception:
        pass


def _get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is not None and str(v).strip() != "":
        return v
    try:
        return st.secrets.get(name, default)  # type: ignore[attr-defined]
    except Exception:
        return default


def get_llm() -> ChatOpenAI:
    api_key = _get_env("DEEPSEEK_API_KEY")
    base_url = _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = _get_env("DEEPSEEK_MODEL", "deepseek-chat")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY (set it in .env or Streamlit secrets).")
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0,
        streaming=True,
    )


def get_retriever():
    cfg = from_env()
    vectordb = load_or_create_chroma(cfg)
    return vectordb.as_retriever(search_kwargs={"k": 4})


def _docs_to_context(docs) -> str:
    return "\n\n".join(d.page_content for d in docs)


def _to_lc_history(ui_messages: list[tuple[str, str]]):
    out = []
    for role, content in ui_messages:
        if role == "human":
            out.append(HumanMessage(content=content))
        elif role == "ai":
            out.append(AIMessage(content=content))
        elif role == "system":
            out.append(SystemMessage(content=content))
    return out


def get_prompts():
    condense_system = (
        "你将把用户的追问改写成一个独立问题，便于检索。"
        "如果没有足够的聊天记录，就直接返回用户问题本身。"
    )
    condense_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", condense_system),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

    qa_system = (
        "你是一个基于知识库的中文问答助手。"
        "请严格使用给定的上下文回答；如果上下文不足以支持结论，就回答“不知道”。"
        "回答要简洁、具体。"
        "\n\n【上下文】\n{context}"
    )
    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", qa_system),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    return condense_prompt, qa_prompt


def gen_response(prompt: str, ui_history: list[tuple[str, str]]):
    retriever = get_retriever()
    llm = get_llm()
    condense_prompt, qa_prompt = get_prompts()

    chat_history = _to_lc_history(ui_history)

    if len(chat_history) == 0:
        query = prompt
    else:
        query = (condense_prompt | llm | StrOutputParser()).invoke(
            {"input": prompt, "chat_history": chat_history}
        )

    docs = retriever.invoke(query)
    context = _docs_to_context(docs)

    answer_chain = qa_prompt | llm | StrOutputParser()
    yield from answer_chain.stream(
        {"input": prompt, "chat_history": chat_history, "context": context}
    )


def _handle_upload_and_index(cfg):
    with st.sidebar:
        st.markdown("### 知识库管理")
        st.write(f"文档目录：`{cfg.docs_dir.as_posix()}`")
        st.write(f"向量库目录：`{cfg.chroma_dir.as_posix()}`")
        st.write(f"Embedding：`{cfg.embedding_provider}` / `{cfg.embedding_model}`")

        uploaded = st.file_uploader(
            "上传本地文档（.txt / .md）",
            type=["txt", "md"],
            accept_multiple_files=True,
        )
        rebuild = st.checkbox("重建向量库（会清空旧库）", value=False)

        clicked = st.button("入库", type="primary", disabled=not uploaded)
        if not clicked:
            return

        saved = 0
        docs: list[Document] = []
        for f in uploaded or []:
            raw = f.getvalue()
            try:
                text = raw.decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="ignore")

            if not text.strip():
                continue

            suffix = Path(f.name).suffix.lower()
            if suffix not in {".txt", ".md"}:
                suffix = ".txt"
            safe_name = f"{Path(f.name).stem}_{uuid4().hex[:8]}{suffix}"
            out_path = cfg.docs_dir / safe_name
            out_path.write_text(text, encoding="utf-8")

            saved += 1
            docs.append(Document(page_content=text, metadata={"source": str(out_path)}))

        with st.spinner("正在建立/更新向量库…"):
            if rebuild:
                rebuild_chroma_from_docs(cfg)
                st.success(f"已保存 {saved} 个文件，并完成向量库重建。")
            else:
                _, added_chunks = add_docs_to_chroma(cfg, docs)
                st.success(f"已保存 {saved} 个文件，并新增 {added_chunks} 个文本块到向量库。")

        st.rerun()


# Streamlit 应用程序界面
def main():
    load_dotenv(".env")
    load_dotenv("api.env")
    _sync_streamlit_secrets_to_env()

    st.markdown("### RAG + DeepSeek（Streamlit）")
    st.caption("支持上传本地文档（txt/md）并一键建立/更新向量库。")

    cfg = from_env()
    cfg.docs_dir.mkdir(parents=True, exist_ok=True)
    _handle_upload_and_index(cfg)

    # 用于跟踪对话历史
    if "messages" not in st.session_state:
        st.session_state.messages = []
    messages = st.container(height=550)
    # 显示整个对话历史
    for message in st.session_state.messages:
            with messages.chat_message(message[0]):
                st.write(message[1])
    if prompt := st.chat_input("Say something"):
        # 将用户输入添加到对话历史中
        st.session_state.messages.append(("human", prompt))
        with messages.chat_message("human"):
            st.write(prompt)

        try:
            with messages.chat_message("ai"):
                output = st.write_stream(gen_response(prompt, st.session_state.messages[:-1]))
            st.session_state.messages.append(("ai", output))
        except Exception as e:
            st.error(str(e))


if __name__ == "__main__":
    main()
