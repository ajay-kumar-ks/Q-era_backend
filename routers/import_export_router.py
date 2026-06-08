"""
Router for bulk import/export of questions and exams.
Supports CSV and Excel file formats.
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
from typing import Optional

from services.import_export_service import ImportExportService
from middlewares.auth import get_current_user as verify_token




router = APIRouter(prefix="/api/v1", tags=["import-export"])


# ============ QUESTION EXPORT ENDPOINTS ============

@router.get("/questions/export/csv", dependencies=[Depends(verify_token)])
async def export_questions_csv(
    question_ids: Optional[str] = Query(None, description="Comma-separated question IDs"),
    current_user: dict = Depends(verify_token)
):
    """
    Export questions to CSV format.
    
    Query Parameters:
    - question_ids: Optional comma-separated list of question IDs to export.
                   If not provided, exports all questions.
    
    Returns:
    - CSV file download
    """
    try:
        ids = None
        if question_ids:
            ids = [int(x.strip()) for x in question_ids.split(",") if x.strip()]
        
        csv_content = await ImportExportService.export_questions_csv(ids)
        
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=questions_export.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/questions/export/excel", dependencies=[Depends(verify_token)])
async def export_questions_excel(
    question_ids: Optional[str] = Query(None, description="Comma-separated question IDs"),
    current_user: dict = Depends(verify_token)
):
    """
    Export questions to Excel format.
    
    Query Parameters:
    - question_ids: Optional comma-separated list of question IDs to export.
                   If not provided, exports all questions.
    
    Returns:
    - Excel file download
    """
    try:
        ids = None
        if question_ids:
            ids = [int(x.strip()) for x in question_ids.split(",") if x.strip()]
        
        excel_bytes = await ImportExportService.export_questions_excel(ids)
        
        return StreamingResponse(
            iter([excel_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=questions_export.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ QUESTION IMPORT ENDPOINTS ============

@router.post("/questions/import/csv", dependencies=[Depends(verify_token)])
async def import_questions_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(verify_token)
):
    """
    Import questions from CSV file.
    
    CSV Format (headers required):
    - id, title, description, type, difficulty, tags, image_url, media_url, attachment_url, created_by
    
    Notes:
    - Tags should be comma-separated or JSON array format
    - URLs are optional
    - Type defaults to 'mcq' if not specified
    - Difficulty defaults to 'medium' if not specified
    
    Returns:
    - {
        "success": bool,
        "imported_count": int,
        "errors": [list of error messages],
        "message": str
      }
    """
    try:
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be CSV format (.csv)")
        
        content = await file.read()
        csv_content = content.decode("utf-8")
        
        count, errors = await ImportExportService.import_questions_csv(
            csv_content, 
            current_user.get("user_id")
        )
        
        return {
            "success": len(errors) == 0 or count > 0,
            "imported_count": count,
            "errors": errors,
            "message": f"Successfully imported {count} questions" + (
                f" with {len(errors)} errors" if errors else ""
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/questions/import/excel", dependencies=[Depends(verify_token)])
async def import_questions_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(verify_token)
):
    """
    Import questions from Excel file.
    
    Excel Format (first sheet, headers required in row 1):
    - ID, Title, Description, Type, Difficulty, Tags, Image URL, Media URL, Attachment URL, Created By
    
    Notes:
    - Tags should be comma-separated or JSON array format
    - URLs are optional
    - Type defaults to 'mcq' if not specified
    - Difficulty defaults to 'medium' if not specified
    
    Returns:
    - {
        "success": bool,
        "imported_count": int,
        "errors": [list of error messages],
        "message": str
      }
    """
    try:
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")
        
        file_bytes = await file.read()
        
        count, errors = await ImportExportService.import_questions_excel(
            file_bytes,
            current_user.get("user_id")
        )
        
        return {
            "success": len(errors) == 0 or count > 0,
            "imported_count": count,
            "errors": errors,
            "message": f"Successfully imported {count} questions" + (
                f" with {len(errors)} errors" if errors else ""
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ EXAM EXPORT ENDPOINTS ============

@router.get("/exams/export/csv", dependencies=[Depends(verify_token)])
async def export_exams_csv(
    exam_ids: Optional[str] = Query(None, description="Comma-separated exam IDs"),
    current_user: dict = Depends(verify_token)
):
    """
    Export exams to CSV format.
    
    Query Parameters:
    - exam_ids: Optional comma-separated list of exam IDs to export.
               If not provided, exports all exams.
    
    Returns:
    - CSV file download
    """
    try:
        ids = None
        if exam_ids:
            ids = [int(x.strip()) for x in exam_ids.split(",") if x.strip()]
        
        csv_content = await ImportExportService.export_exams_csv(ids)
        
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=exams_export.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exams/export/excel", dependencies=[Depends(verify_token)])
async def export_exams_excel(
    exam_ids: Optional[str] = Query(None, description="Comma-separated exam IDs"),
    current_user: dict = Depends(verify_token)
):
    """
    Export exams to Excel format.
    
    Query Parameters:
    - exam_ids: Optional comma-separated list of exam IDs to export.
               If not provided, exports all exams.
    
    Returns:
    - Excel file download
    """
    try:
        ids = None
        if exam_ids:
            ids = [int(x.strip()) for x in exam_ids.split(",") if x.strip()]
        
        excel_bytes = await ImportExportService.export_exams_excel(ids)
        
        return StreamingResponse(
            iter([excel_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=exams_export.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ EXAM IMPORT ENDPOINTS ============

@router.post("/exams/import/csv", dependencies=[Depends(verify_token)])
async def import_exams_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(verify_token)
):
    """
    Import exams from CSV file.
    
    CSV Format (headers required):
    - id, title, description, duration_minutes, total_marks, passing_marks, secure_mode, is_public, created_by
    
    Notes:
    - duration_minutes defaults to 60
    - total_marks defaults to 100
    - passing_marks defaults to 50
    - secure_mode and is_public should be 'yes', 'no', 'true', 'false', '1', or '0'
    
    Returns:
    - {
        "success": bool,
        "imported_count": int,
        "errors": [list of error messages],
        "message": str
      }
    """
    try:
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be CSV format (.csv)")
        
        content = await file.read()
        csv_content = content.decode("utf-8")
        
        count, errors = await ImportExportService.import_exams_csv(
            csv_content,
            current_user.get("user_id")
        )
        
        return {
            "success": len(errors) == 0 or count > 0,
            "imported_count": count,
            "errors": errors,
            "message": f"Successfully imported {count} exams" + (
                f" with {len(errors)} errors" if errors else ""
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exams/import/excel", dependencies=[Depends(verify_token)])
async def import_exams_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(verify_token)
):
    """
    Import exams from Excel file.
    
    Excel Format (first sheet, headers required in row 1):
    - ID, Title, Description, Duration (mins), Total Marks, Passing Marks, Secure Mode, Is Public, Created By
    
    Notes:
    - Duration defaults to 60 minutes
    - Total marks defaults to 100
    - Passing marks defaults to 50
    - Secure Mode and Is Public should be 'Yes', 'No', '1', or '0'
    
    Returns:
    - {
        "success": bool,
        "imported_count": int,
        "errors": [list of error messages],
        "message": str
      }
    """
    try:
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")
        
        file_bytes = await file.read()
        
        count, errors = await ImportExportService.import_exams_excel(
            file_bytes,
            current_user.get("user_id")
        )
        
        return {
            "success": len(errors) == 0 or count > 0,
            "imported_count": count,
            "errors": errors,
            "message": f"Successfully imported {count} exams" + (
                f" with {len(errors)} errors" if errors else ""
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
