from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models
from ..deps import get_current_user
from ..schemas import ProjectCreate, ProjectOut

router = APIRouter()



@router.get("/", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).order_by(models.Project.id).all()
    return projects


@router.post("/create", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    project = models.Project(
        project_type=payload.project_type,
        client_name=payload.client_name,
        location=payload.location,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

