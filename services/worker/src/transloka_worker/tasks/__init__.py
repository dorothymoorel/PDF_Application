from transloka_worker.tasks.ocr import OCR_TASK_NAME, register_ocr_task
from transloka_worker.tasks.reconstruction import (
    RECONSTRUCTION_TASK_NAME,
    register_reconstruction_task,
)
from transloka_worker.tasks.translation import (
    TRANSLATION_TASK_NAME,
    register_translation_task,
)

__all__ = [
    "OCR_TASK_NAME",
    "RECONSTRUCTION_TASK_NAME",
    "TRANSLATION_TASK_NAME",
    "register_ocr_task",
    "register_reconstruction_task",
    "register_translation_task",
]
