import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

from autenticacao import router as rotas_de_autenticacao
from autenticacao import usuario_atual
from banco import criar_tabelas

MODELO = "openrouter/free"  # roteador que escolhe um modelo gratuito disponivel
MAX_TOKENS = 2000  # limite da resposta; sem ele o OpenRouter reserva o maximo do modelo

load_dotenv()  # carrega as variaveis do arquivo .env
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_KEY"))


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    criar_tabelas()  # cria o que faltar ao subir; nao altera tabelas que ja existem
    yield


app = FastAPI(lifespan=ciclo_de_vida)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"null|http://(localhost|127\.0\.0\.1)(:\d+)?",  # index.html aberto direto (null) ou servido localmente
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(rotas_de_autenticacao)


class Mensagem(BaseModel):
    message: str


@app.post("/send_message", dependencies=[Depends(usuario_atual)])
def send_message(mensagem: Mensagem):
    resposta = client.chat.completions.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": mensagem.message}],
    )
    return {"response": resposta.choices[0].message.content}
