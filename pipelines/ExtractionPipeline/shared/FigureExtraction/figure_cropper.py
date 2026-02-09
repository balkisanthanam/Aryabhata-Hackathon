"""
Figure Cropper - Crops figure images from page images using bounding boxes.

Pure Python/PIL implementation (no AI) - follows the pattern from
ImageBasedExtraction/step4_crop_questions.py.

Usage:
    cropper = FigureCropper()
    cropped_image = cropper.crop_figure(page_image, bbox)
    cropper.crop_and_save(page_image, bbox, output_path)
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple
from dataclasses import dataclass
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class CropperConfig:
    """Configuration for FigureCropper."""
    padding_pixels: int = 5  # Additional padding after converting from normalized
    output_format: str = "PNG"
    quality: int = 95  # For JPEG
    min_size: int = 20  # Minimum dimension in pixels (skip tiny crops)


class FigureCropper:
    """
    Crops figures from page images using normalized bounding boxes.
    
    Bounding boxes are in [ymin, xmin, ymax, xmax] format with 0-1000 scale.
    """
    
    def __init__(self, config: Optional[CropperConfig] = None):
        """
        Initialize the figure cropper.
        
        Args:
            config: Configuration options. If None, uses defaults.
        """
        self.config = config or CropperConfig()
    
    def normalize_to_pixels(
        self,
        bbox: List[int],
        image_width: int,
        image_height: int
    ) -> Tuple[int, int, int, int]:
        """
        Convert normalized 0-1000 coordinates to pixel coordinates.
        
        Args:
            bbox: [ymin, xmin, ymax, xmax] in 0-1000 scale
            image_width: Actual image width in pixels
            image_height: Actual image height in pixels
            
        Returns:
            Tuple of (xmin_px, ymin_px, xmax_px, ymax_px) for PIL crop
        """
        ymin_norm, xmin_norm, ymax_norm, xmax_norm = bbox
        
        # Convert from normalized to pixels
        ymin_px = int((ymin_norm / 1000) * image_height)
        xmin_px = int((xmin_norm / 1000) * image_width)
        ymax_px = int((ymax_norm / 1000) * image_height)
        xmax_px = int((xmax_norm / 1000) * image_width)
        
        # Add padding
        padding = self.config.padding_pixels
        xmin_px = max(0, xmin_px - padding)
        ymin_px = max(0, ymin_px - padding)
        xmax_px = min(image_width, xmax_px + padding)
        ymax_px = min(image_height, ymax_px + padding)
        
        return (xmin_px, ymin_px, xmax_px, ymax_px)
    
    def crop_figure(
        self,
        image: Union[Image.Image, Path, str],
        bbox: List[int]
    ) -> Optional[Image.Image]:
        """
        Crop a figure from a page image using normalized bounding box.
        
        Args:
            image: PIL Image or path to image file
            bbox: [ymin, xmin, ymax, xmax] in 0-1000 normalized scale
            
        Returns:
            Cropped PIL Image, or None if crop is invalid/too small
        """
        # Load image if path provided
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        
        width, height = image.size
        
        # Convert to pixel coordinates
        xmin, ymin, xmax, ymax = self.normalize_to_pixels(bbox, width, height)
        
        # Validate crop dimensions
        crop_width = xmax - xmin
        crop_height = ymax - ymin
        
        if crop_width < self.config.min_size or crop_height < self.config.min_size:
            logger.warning(f"Crop too small: {crop_width}x{crop_height}px, skipping")
            return None
        
        # PIL crop uses (left, upper, right, lower) = (xmin, ymin, xmax, ymax)
        cropped = image.crop((xmin, ymin, xmax, ymax))
        
        logger.debug(f"Cropped figure: {crop_width}x{crop_height}px from bbox {bbox}")
        return cropped
    
    def crop_and_save(
        self,
        image: Union[Image.Image, Path, str],
        bbox: List[int],
        output_path: Union[Path, str],
        convert_to_rgb: bool = True
    ) -> Optional[Path]:
        """
        Crop a figure and save to file.
        
        Args:
            image: PIL Image or path to image file
            bbox: [ymin, xmin, ymax, xmax] in 0-1000 normalized scale
            output_path: Path to save the cropped image
            convert_to_rgb: Convert to RGB before saving (needed for JPEG)
            
        Returns:
            Path to saved file, or None if crop failed
        """
        cropped = self.crop_figure(image, bbox)
        if cropped is None:
            return None
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to RGB if needed (for JPEG format)
        if convert_to_rgb and cropped.mode in ('RGBA', 'P', 'LA'):
            # Create white background
            background = Image.new('RGB', cropped.size, (255, 255, 255))
            if cropped.mode == 'RGBA':
                background.paste(cropped, mask=cropped.split()[3])
            else:
                background.paste(cropped)
            cropped = background
        
        # Save based on format
        fmt = self.config.output_format.upper()
        if fmt == 'PNG':
            cropped.save(output_path, 'PNG', optimize=True)
        elif fmt in ('JPG', 'JPEG'):
            cropped.save(output_path, 'JPEG', quality=self.config.quality, optimize=True)
        else:
            cropped.save(output_path)
        
        logger.info(f"Saved cropped figure: {output_path}")
        return output_path
    
    def crop_multiple(
        self,
        page_images: Dict[int, Union[Image.Image, Path, str]],
        figures: List[Dict],
        output_dir: Union[Path, str],
        naming_pattern: str = "fig_{page}_{label}.png"
    ) -> List[Dict]:
        """
        Crop multiple figures from their respective page images.
        
        Args:
            page_images: Dict mapping page_index to image
            figures: List of figure dicts with 'box_2d', 'page_index', 'label'
            output_dir: Directory to save cropped images
            naming_pattern: Pattern for filenames (supports {page}, {label}, {idx})
            
        Returns:
            List of dicts with crop results including file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        for idx, fig in enumerate(figures):
            page_idx = fig.get('page_index', 0)
            bbox = fig.get('box_2d', [])
            label = fig.get('label', 'unlabeled')
            page_num = fig.get('page_number', page_idx + 1)
            
            # Get page image
            if page_idx not in page_images:
                logger.warning(f"Page image not found for index {page_idx}")
                results.append({**fig, 'cropped_path': None, 'error': 'page_not_found'})
                continue
            
            # Generate filename
            safe_label = label.replace(' ', '_').replace('.', '_').replace('/', '-')
            filename = naming_pattern.format(
                page=page_num,
                label=safe_label,
                idx=idx
            )
            output_path = output_dir / filename
            
            # Crop and save
            saved_path = self.crop_and_save(
                image=page_images[page_idx],
                bbox=bbox,
                output_path=output_path
            )
            
            results.append({
                **fig,
                'cropped_path': str(saved_path) if saved_path else None,
                'error': None if saved_path else 'crop_failed'
            })
        
        success_count = sum(1 for r in results if r.get('cropped_path'))
        logger.info(f"Cropped {success_count}/{len(figures)} figures to {output_dir}")
        
        return results
    
    def stitch_figures_vertically(
        self,
        images: List[Image.Image],
        background_color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        Stitch multiple figure images vertically (for multi-page figures).
        
        Args:
            images: List of PIL Images to stitch
            background_color: RGB color for background padding
            
        Returns:
            Single stitched PIL Image
        """
        if not images:
            raise ValueError("No images to stitch")
        
        if len(images) == 1:
            return images[0]
        
        # Calculate total dimensions
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        
        # Create canvas
        stitched = Image.new('RGB', (max_width, total_height), background_color)
        
        # Paste images
        y_offset = 0
        for img in images:
            # Convert if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            stitched.paste(img, (0, y_offset))
            y_offset += img.height
        
        logger.info(f"Stitched {len(images)} images: {max_width}x{total_height}px")
        return stitched
