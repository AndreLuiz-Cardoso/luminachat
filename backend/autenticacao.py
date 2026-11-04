import hashlib
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, select

from banco import Sessao, Usuario, abrir_banco, agora, engine

DURACAO_DA_SESSAO = timedelta(days=30)

hasher = PasswordHash.recommended()  # Argon2
HASH_FALSO = hasher.hash("senha-de-ninguem")  # usuario inexistente gasta o mesmo tempo que senha errada
bearer = HTTPBearer(auto_error=False)
router = APIRouter()

Banco = Annotated[Session, Depends(abrir_banco)]
Credencial = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


class Login(BaseModel):
    username: str = Field(max_length=32)
    password: str = Field(max_length=128)  # o limite evita gastar CPU com hash de textos enormes


class Cadastro(Login):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)


def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def nao_autorizado(detalhe: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detalhe, headers={"WWW-Authenticate": "Bearer"})


def abrir_sessao(banco: Session, usuario: Usuario) -> dict:
    token = secrets.token_urlsafe(32)
    banco.add(Sessao(token_hash=hash_do_token(token), usuario_id=usuario.id, expira_em=agora() + DURACAO_DA_SESSAO))
    banco.commit()
    return {"token": token, "username": usuario.username}


def usuario_atual(credencial: Credencial) -> Usuario:
    # conexao propria e curta: nao pode ficar presa durante a chamada ao modelo, que leva segundos
    with Session(engine) as banco:
        sessao = banco.get(Sessao, hash_do_token(credencial.credentials)) if credencial else None
        if not sessao or sessao.expira_em < agora():
            raise nao_autorizado("Sessao invalida ou expirada")
        return banco.get(Usuario, sessao.usuario_id)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(dados: Cadastro, banco: Banco):
    usuario = Usuario(username=dados.username.lower(), senha_hash=hasher.hash(dados.password))
    banco.add(usuario)
    try:
        banco.commit()
    except IntegrityError:  # o indice unico decide, mesmo com dois cadastros ao mesmo tempo
        banco.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Usuario ja existe") from None
    banco.refresh(usuario)
    return abrir_sessao(banco, usuario)


@router.post("/login")
def login(dados: Login, banco: Banco):
    usuario = banco.exec(select(Usuario).where(Usuario.username == dados.username.lower())).first()
    valida, hash_novo = hasher.verify_and_update(dados.password, usuario.senha_hash if usuario else HASH_FALSO)
    if not usuario or not valida:
        raise nao_autorizado("Usuario ou senha incorretos")
    if hash_novo:  # atualiza senhas antigas quando os parametros do Argon2 mudam
        usuario.senha_hash = hash_novo
        banco.add(usuario)
    banco.exec(delete(Sessao).where(Sessao.expira_em < agora()))  # limpeza sem precisar de tarefa agendada
    return abrir_sessao(banco, usuario)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(credencial: Credencial, banco: Banco):
    if credencial:
        banco.exec(delete(Sessao).where(Sessao.token_hash == hash_do_token(credencial.credentials)))
        banco.commit()


@router.get("/me")
def me(usuario: Annotated[Usuario, Depends(usuario_atual)]):
    return {"username": usuario.username}
