import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router
from config import Settings 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],    
    allow_headers=["*"],    
)

# Include the router
app.include_router(router)



if __name__ == "__main__":
    settings = Settings()
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
