import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from autenticacao import router as rotas_de_autenticacao
from autenticacao import usuario_atual
from banco import criar_tabelas

MODELO = "openrouter/free"  # router that picks an available free model
MAX_TOKENS = 2000  # response limit; without it OpenRouter reserves the model's maximum
FRONTEND = Path(__file__).parent / "frontend"

load_dotenv()  # loads the variables from the .env file
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_KEY"))


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    criar_tabelas()  # creates whatever is missing on startup; never alters existing tables
    yield


app = FastAPI(lifespan=ciclo_de_vida)
app.include_router(rotas_de_autenticacao)
# publish only the frontend's assets: this project's folder also holds .env and the database
app.mount(
    "/lumina-video-design-system",
    StaticFiles(directory=FRONTEND / "lumina-video-design-system"),
    name="design-system",
)


class Mensagem(BaseModel):
    message: str


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND / "index.html")


@app.post("/send_message", dependencies=[Depends(usuario_atual)])
def send_message(mensagem: Mensagem):
    resposta = client.chat.completions.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": mensagem.message}],
    )
    return {"response": resposta.choices[0].message.content}
