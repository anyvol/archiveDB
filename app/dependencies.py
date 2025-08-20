# dependencies.py
from fastapi import FastAPI, Security
from fastapi.security import OAuth2PasswordBearer, OAuth2AuthorizationCodeBearer
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.security.oauth2 import OAuth2
from fastapi.openapi.utils import get_openapi

app = FastAPI()

class OAuth2PasswordBearerWithCookie(OAuth2):
    def __init__(self, tokenUrl: str):
        flows = OAuthFlowsModel(password={"tokenUrl": tokenUrl})
        super().__init__(flows=flows, scheme_name="OAuth2PasswordBearer")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="ArchiveDB API",
        version="1.0.0",
        description="API for ArchiveDB",
        routes=app.routes,
    )
    # Добавляем security scheme в схему
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/users/login",
                    "scopes": {}
                }
            }
        }
    }
    # Добавляем требование security для всех защищённых путей автоматически необязательно
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi