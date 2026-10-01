# app.py
import streamlit as st
import os
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from prompts import SDLC_PHASES, get_system_prompt
import tempfile

# 1. Configuración de la página
st.set_page_config(page_title="IA Software Architect", page_icon="⚙️", layout="wide")
st.title("Asistente IA - Ciclo de Vida de Software & Cumplimiento Normativo")

# 2. Inicialización de Estado de Sesión
if "messages" not in st.session_state:
    st.session_state.messages = []
if "vector_store" not in st.session_state:
    st.session_state.vector_store = None

# 3. Barra Lateral: Configuración y Carga de Archivos
with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("OpenAI API Key", type="password")
    os.environ["OPENAI_API_KEY"] = api_key
    
    st.header("Fase del Proyecto")
    current_phase = st.selectbox("Selecciona la etapa actual:", list(SDLC_PHASES.keys()))
    
    st.header("Documentación Técnica / Normativas")
    st.write("Sube manuales, contratos o normas (ej. ISO 29119) para validación.")
    uploaded_files = st.file_uploader("Cargar PDF/TXT", accept_multiple_files=True, type=['pdf', 'txt'])
    
    if st.button("Procesar Documentos") and uploaded_files and api_key:
        with st.spinner("Procesando y vectorizando documentos..."):
            documents = []
            for file in uploaded_files:
                # Guardar temporalmente para que LangChain lo lea
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.name.split('.')[-1]}") as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = tmp.name
                
                # Cargar dependiendo del tipo
                if file.name.endswith('.pdf'):
                    loader = PyPDFLoader(tmp_path)
                else:
                    loader = TextLoader(tmp_path)
                documents.extend(loader.load())
            
            # Dividir texto en chunks manejables (RAG)
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = text_splitter.split_documents(documents)
            
            # Crear Base de Datos Vectorial
            embeddings = OpenAIEmbeddings()
            st.session_state.vector_store = FAISS.from_documents(chunks, embeddings)
            st.success("Documentos procesados e indexados correctamente.")

# 4. Interfaz de Chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 5. Lógica de Respuesta RAG y Generación
if prompt := st.chat_input("Escribe tu requerimiento o haz una pregunta sobre la normativa..."):
    if not api_key:
        st.error("Por favor, ingresa tu API Key en la barra lateral.")
        st.stop()
        
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.2)
        system_prompt = get_system_prompt(current_phase)
        
        # Si hay documentos cargados, usamos RAG
        if st.session_state.vector_store:
            retriever = st.session_state.vector_store.as_retriever(search_kwargs={"k": 5})
            
            qa_system_prompt = system_prompt + "\n\nContexto normativo/técnico:\n{context}"
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", qa_system_prompt),
                ("human", "{input}")
            ])
            
            question_answer_chain = create_stuff_documents_chain(llm, prompt_template)
            rag_chain = create_retrieval_chain(retriever, question_answer_chain)
            
            with st.spinner("Consultando normativas y generando respuesta..."):
                response = rag_chain.invoke({"input": prompt})
                full_response = response["answer"]
                
        # Si no hay documentos, usamos conversación estándar guiada por la fase
        else:
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}")
            ])
            chain = prompt_template | llm
            with st.spinner("Analizando requerimientos..."):
                response = chain.invoke({"input": prompt})
                full_response = response.content
        
        st.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
