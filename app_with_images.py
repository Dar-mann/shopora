
"""
SHOPORA CLOUDINARY PRODUCT IMAGE SERVICE

Copyright (c) 2026 Computer Software Group 1.
All rights reserved.

This module extends the existing Shopora FastAPI backend
with authenticated product image uploads.

Cloudinary Cloud Name: obpyhqy1

Required Render environment variables:
    CLOUDINARY_URL
    DATABASE_URL
    SHOPORA_SECRET_KEY

Render start command:
    uvicorn app_with_images:app --host 0.0.0.0 --port $PORT

Supported formats:
    JPEG, PNG, WebP

Maximum upload size:
    5 MB
"""

import io
import os

import cloudinary
import cloudinary.uploader

from fastapi import (
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from fastapi.responses import RedirectResponse

from PIL import Image, UnidentifiedImageError

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
)

from starlette.concurrency import run_in_threadpool

import main as shopora_backend
import models

from database import (
    Base,
    SessionLocal,
    engine,
)


# ============================================================
# EXISTING SHOPORA APPLICATION
# ============================================================

# Reuse the existing website backend.
# This preserves customer authentication, seller accounts,
# products, shopping carts, checkout, and orders.

app = shopora_backend.app


# ============================================================
# CONFIGURATION
# ============================================================

MAX_IMAGE_BYTES = 5 * 1024 * 1024

ALLOWED_IMAGE_FORMATS = {
    "JPEG",
    "PNG",
    "WEBP",
}

CLOUDINARY_URL = os.environ.get(
    "CLOUDINARY_URL",
    "",
).strip()

CLOUDINARY_CLOUD_NAME = "obpyhqy1"

if CLOUDINARY_URL:
    cloudinary.config(
        secure=True,
    )


# ============================================================
# DATABASE MODEL FOR PRODUCT IMAGES
# ============================================================

class ProductPhoto(Base):
    __tablename__ = "product_photos"

    product_id = Column(
        Integer,
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    image_url = Column(
        String(2048),
        nullable=False,
    )

    public_id = Column(
        String(512),
        nullable=False,
    )


# Create the image table without deleting existing products.
# This requires DATABASE_URL to point to the correct database.

Base.metadata.create_all(
    bind=engine,
    tables=[ProductPhoto.__table__],
)


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_product_image(raw: bytes):
    """
    Validate image size, format, and dimensions.
    """

    if not raw:
        raise HTTPException(
            status_code=422,
            detail="The selected image is empty.",
        )

    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Maximum image size is 5 MB.",
        )

    try:
        with Image.open(io.BytesIO(raw)) as picture:
            picture.verify()

        with Image.open(io.BytesIO(raw)) as picture:
            image_format = picture.format
            width, height = picture.size

    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ):
        raise HTTPException(
            status_code=422,
            detail="The selected file is not a valid image.",
        )

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unsupported image format. "
                "Use JPG, PNG, or WebP."
            ),
        )

    if width <= 0 or height <= 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid image dimensions.",
        )

    if width * height > 25_000_000:
        raise HTTPException(
            status_code=422,
            detail="Image dimensions are too large.",
        )

    return image_format


# ============================================================
# CLOUDINARY UPLOAD HELPER
# ============================================================

def upload_to_cloudinary(raw: bytes):
    """
    Upload a validated product photograph to Cloudinary.
    """

    if not CLOUDINARY_URL:
        raise HTTPException(
            status_code=503,
            detail="Cloudinary is not configured on Render.",
        )

    try:
        result = cloudinary.uploader.upload(
            raw,
            resource_type="image",
            folder="shopora/products",
            overwrite=False,
        )

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Cloudinary rejected the upload. "
                "Check the Render backend logs."
            ),
        ) from error

    image_url = result.get("secure_url")
    public_id = result.get("public_id")

    if (
        not isinstance(image_url, str)
        or not image_url.startswith("https://")
        or not isinstance(public_id, str)
        or not public_id
    ):
        raise HTTPException(
            status_code=502,
            detail="Cloudinary returned invalid image information.",
        )

    return {
        "image_url": image_url,
        "public_id": public_id,
    }


# ============================================================
# SELLER PRODUCT IMAGE UPLOAD
# ============================================================

@app.post(
    "/seller/products/{product_id}/image"
)
async def upload_product_image(
    product_id: int,
    image: UploadFile = File(...),
    seller: dict = Depends(
        shopora_backend.get_current_seller
    ),
):
    """
    Allows an authenticated seller to upload
    or replace a photograph for their own product.

    Flutter request:
      POST /seller/products/{product_id}/image

    Authentication:
      Authorization: Bearer SELLER_TOKEN

    Multipart field:
      image
    """

    if not CLOUDINARY_URL:
        raise HTTPException(
            status_code=503,
            detail="Cloudinary storage is not configured.",
        )

    db = SessionLocal()

    try:
        # ----------------------------------------------------
        # CHECK SELLER OWNERSHIP
        # ----------------------------------------------------

        product = (
            db.query(models.Product)
            .filter(
                models.Product.id == product_id,
                models.Product.seller_id == seller["id"],
            )
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Product not found or this seller "
                    "does not own the product."
                ),
            )

        # ----------------------------------------------------
        # READ AND VALIDATE IMAGE
        # ----------------------------------------------------

        raw = await image.read(
            MAX_IMAGE_BYTES + 1
        )

        validate_product_image(raw)

        # ----------------------------------------------------
        # UPLOAD IMAGE TO CLOUDINARY
        # ----------------------------------------------------

        uploaded = await run_in_threadpool(
            upload_to_cloudinary,
            raw,
        )

        image_url = uploaded["image_url"]
        public_id = uploaded["public_id"]

        # ----------------------------------------------------
        # SAVE PHOTO IN DATABASE
        # ----------------------------------------------------

        photo = db.get(
            ProductPhoto,
            product_id,
        )

        previous_public_id = (
            photo.public_id
            if photo is not None
            else None
        )

        if photo is None:
            photo = ProductPhoto(
                product_id=product_id,
                image_url=image_url,
                public_id=public_id,
            )

            db.add(photo)

        else:
            photo.image_url = image_url
            photo.public_id = public_id

        try:
            db.commit()

        except Exception:
            db.rollback()

            # Clean up the newly uploaded image if the
            # database transaction fails.
            try:
                await run_in_threadpool(
                    cloudinary.uploader.destroy,
                    public_id,
                )
            except Exception:
                pass

            raise HTTPException(
                status_code=500,
                detail="Could not save product image.",
            )

        # ----------------------------------------------------
        # REMOVE REPLACED IMAGE FROM CLOUDINARY
        # ----------------------------------------------------

        if (
            previous_public_id
            and previous_public_id != public_id
        ):
            try:
                await run_in_threadpool(
                    cloudinary.uploader.destroy,
                    previous_public_id,
                )
            except Exception:
                # The new image remains saved even if
                # cleanup of the old one fails.
                pass

        # ----------------------------------------------------
        # SUCCESS RESPONSE
        # ----------------------------------------------------

        return {
            "success": True,
            "message": "Product photo uploaded successfully.",
            "product_id": product_id,
            "image_url": image_url,
        }

    finally:
        await image.close()
        db.close()


# ============================================================
# PUBLIC PRODUCT IMAGE ENDPOINT
# ============================================================

@app.get(
    "/products/{product_id}/image"
)
def get_product_image(
    product_id: int,
):
    """
    Retrieves a product image URL from the database
    and redirects the client to Cloudinary.
    """

    db = SessionLocal()

    try:
        photo = db.get(
            ProductPhoto,
            product_id,
        )

        if photo is None:
            raise HTTPException(
                status_code=404,
                detail="No photograph found for this product.",
            )

        return RedirectResponse(
            url=photo.image_url,
            status_code=307,
        )

    finally:
        db.close()


# ============================================================
# CLOUDINARY STATUS ENDPOINT
# ============================================================

@app.get(
    "/image-upload/status"
)
def image_upload_status():
    """
    Confirm the image extension is loaded.

    This checks configuration, not whether an
    actual Cloudinary upload will succeed.
    """

    configured = bool(CLOUDINARY_URL)

    return {
        "service": "Shopora Product Images",
        "status": (
            "ready"
            if configured
            else "unconfigured"
        ),
        "cloud_name": CLOUDINARY_CLOUD_NAME,
        "cloudinary_configured": configured,
        "max_upload_mb": 5,
        "supported_formats": [
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
    }

