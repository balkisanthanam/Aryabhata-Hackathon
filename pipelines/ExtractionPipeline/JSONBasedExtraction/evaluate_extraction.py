"""
JSON-Based Extraction Evaluation Tool

This script compares the output from run_json_extraction.py against manually verified model outputs.
It performs deep comparison of JSON structures and optionally compares extracted figure images.

Usage:
    python evaluate_extraction.py --test-dir <path_to_test_run> --model-dir <path_to_model_run>
"""

import json
import argparse
import difflib
from pathlib import Path
from typing import Dict, List, Tuple, Any, Set
from collections import defaultdict
from datetime import datetime
import re

# Try to import numpy for type checking (optional)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Try to import image comparison libraries (optional)
try:
    from PIL import Image, ImageChops
    import imagehash
    IMAGE_COMPARISON_AVAILABLE = True
except ImportError:
    IMAGE_COMPARISON_AVAILABLE = False


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types, Path objects, and other non-serializable types."""
    def default(self, obj):
        # Handle numpy types if numpy is available
        if HAS_NUMPY:
            if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
        
        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)
        
        # Handle any integer types that might not be standard int
        if hasattr(obj, '__int__'):
            try:
                return int(obj)
            except:
                pass
        
        # Handle any float types that might not be standard float
        if hasattr(obj, '__float__'):
            try:
                return float(obj)
            except:
                pass
        
        return super().default(obj)


class JSONComparator:
    """Compares two JSON structures with flexible matching."""
    
    def __init__(self, ignore_whitespace=True, case_sensitive=True):
        self.ignore_whitespace = ignore_whitespace
        self.case_sensitive = case_sensitive
        self.differences = []
        self.stats = {
            'total_fields': 0,
            'matching_fields': 0,
            'different_fields': 0,
            'missing_fields': 0,
            'extra_fields': 0
        }
    
    def normalize_value(self, value: Any) -> Any:
        """Normalize a value for comparison."""
        if isinstance(value, str):
            # Normalize whitespace if requested
            if self.ignore_whitespace:
                value = ' '.join(value.split())
            # Normalize case if requested
            if not self.case_sensitive:
                value = value.lower()
        return value
    
    def compare_strings(self, val1: str, val2: str, path: str) -> bool:
        """Compare two strings with normalized values and compute similarity."""
        norm_val1 = self.normalize_value(val1)
        norm_val2 = self.normalize_value(val2)
        
        if norm_val1 == norm_val2:
            return True
        
        # Calculate similarity ratio
        similarity = difflib.SequenceMatcher(None, norm_val1, norm_val2).ratio()
        
        self.differences.append({
            'path': path,
            'type': 'value_mismatch',
            'model_value': val1,
            'test_value': val2,
            'similarity': round(similarity * 100, 2)
        })
        return False
    
    def compare_values(self, val1: Any, val2: Any, path: str) -> bool:
        """Compare two values recursively."""
        # Handle None cases
        if val1 is None and val2 is None:
            return True
        if val1 is None or val2 is None:
            self.differences.append({
                'path': path,
                'type': 'null_mismatch',
                'model_value': val1,
                'test_value': val2
            })
            return False
        
        # Handle type mismatches
        if type(val1) != type(val2):
            self.differences.append({
                'path': path,
                'type': 'type_mismatch',
                'model_type': type(val1).__name__,
                'test_type': type(val2).__name__,
                'model_value': str(val1),
                'test_value': str(val2)
            })
            return False
        
        # Handle different types
        if isinstance(val1, dict):
            return self.compare_dicts(val1, val2, path)
        elif isinstance(val1, list):
            return self.compare_lists(val1, val2, path)
        elif isinstance(val1, str):
            self.stats['total_fields'] += 1
            result = self.compare_strings(val1, val2, path)
            if result:
                self.stats['matching_fields'] += 1
            else:
                self.stats['different_fields'] += 1
            return result
        else:
            # Numbers, booleans, etc.
            self.stats['total_fields'] += 1
            if val1 == val2:
                self.stats['matching_fields'] += 1
                return True
            else:
                self.differences.append({
                    'path': path,
                    'type': 'value_mismatch',
                    'model_value': val1,
                    'test_value': val2,
                    'similarity': 0
                })
                self.stats['different_fields'] += 1
                return False
    
    def compare_dicts(self, dict1: Dict, dict2: Dict, path: str = "root") -> bool:
        """Compare two dictionaries recursively."""
        all_keys = set(dict1.keys()) | set(dict2.keys())
        all_match = True
        
        for key in all_keys:
            current_path = f"{path}.{key}" if path != "root" else key
            
            if key not in dict1:
                self.stats['missing_fields'] += 1
                self.differences.append({
                    'path': current_path,
                    'type': 'missing_in_model',
                    'test_value': dict2[key]
                })
                all_match = False
            elif key not in dict2:
                self.stats['extra_fields'] += 1
                self.differences.append({
                    'path': current_path,
                    'type': 'missing_in_test',
                    'model_value': dict1[key]
                })
                all_match = False
            else:
                if not self.compare_values(dict1[key], dict2[key], current_path):
                    all_match = False
        
        return all_match
    
    def compare_lists(self, list1: List, list2: List, path: str) -> bool:
        """Compare two lists element by element."""
        if len(list1) != len(list2):
            self.differences.append({
                'path': path,
                'type': 'list_length_mismatch',
                'model_length': len(list1),
                'test_length': len(list2)
            })
            # Continue comparing available elements
        
        all_match = True
        max_len = max(len(list1), len(list2))
        
        for i in range(max_len):
            current_path = f"{path}[{i}]"
            
            if i >= len(list1):
                self.stats['missing_fields'] += 1
                self.differences.append({
                    'path': current_path,
                    'type': 'missing_in_model',
                    'test_value': list2[i]
                })
                all_match = False
            elif i >= len(list2):
                self.stats['extra_fields'] += 1
                self.differences.append({
                    'path': current_path,
                    'type': 'missing_in_test',
                    'model_value': list1[i]
                })
                all_match = False
            else:
                if not self.compare_values(list1[i], list2[i], current_path):
                    all_match = False
        
        return all_match
    
    def get_match_percentage(self) -> float:
        """Calculate overall match percentage."""
        total = self.stats['total_fields']
        if total == 0:
            return 100.0
        return (self.stats['matching_fields'] / total) * 100


class ImageComparator:
    """Compares extracted figure images."""
    
    def __init__(self):
        self.results = []
    
    def compare_images_perceptual(self, img1_path: Path, img2_path: Path) -> Dict:
        """Compare images using perceptual hashing."""
        if not IMAGE_COMPARISON_AVAILABLE:
            return {
                'method': 'perceptual_hash',
                'status': 'unavailable',
                'message': 'PIL and imagehash libraries not available'
            }
        
        try:
            hash1 = imagehash.average_hash(Image.open(img1_path))
            hash2 = imagehash.average_hash(Image.open(img2_path))
            
            # Hash difference (0 = identical, higher = more different)
            diff = hash1 - hash2
            similarity = max(0, 100 - (diff * 2))  # Convert to percentage
            
            return {
                'method': 'perceptual_hash',
                'status': 'success',
                'similarity': similarity,
                'hash_difference': diff,
                'match': diff <= 5  # Threshold for "similar" images
            }
        except Exception as e:
            return {
                'method': 'perceptual_hash',
                'status': 'error',
                'error': str(e)
            }
    
    def compare_images_pixel(self, img1_path: Path, img2_path: Path) -> Dict:
        """Compare images pixel by pixel."""
        if not IMAGE_COMPARISON_AVAILABLE:
            return {
                'method': 'pixel_comparison',
                'status': 'unavailable'
            }
        
        try:
            img1 = Image.open(img1_path)
            img2 = Image.open(img2_path)
            
            # Check dimensions
            if img1.size != img2.size:
                return {
                    'method': 'pixel_comparison',
                    'status': 'size_mismatch',
                    'model_size': img1.size,
                    'test_size': img2.size,
                    'match': False
                }
            
            # Calculate pixel difference
            diff = ImageChops.difference(img1, img2)
            stat = diff.getbbox()
            
            if stat is None:
                # Images are identical
                similarity = 100.0
            else:
                # Calculate similarity based on difference extent
                diff_pixels = sum(diff.getdata()) if hasattr(diff.getdata(), '__iter__') else 0
                total_pixels = img1.size[0] * img1.size[1] * len(img1.getbands())
                similarity = 100 - (diff_pixels / total_pixels * 100)
            
            return {
                'method': 'pixel_comparison',
                'status': 'success',
                'similarity': round(similarity, 2),
                'match': similarity >= 95
            }
        except Exception as e:
            return {
                'method': 'pixel_comparison',
                'status': 'error',
                'error': str(e)
            }


class EvaluationReport:
    """Generates evaluation reports."""
    
    def __init__(self, model_file: Path, test_file: Path):
        self.model_file = model_file
        self.test_file = test_file
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def generate_text_report(self, comparator: JSONComparator, 
                            image_results: List[Dict], 
                            output_path: Path):
        """Generate a detailed text report."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("JSON-BASED EXTRACTION EVALUATION REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Model File: {self.model_file}\n")
            f.write(f"Test File: {self.test_file}\n\n")
            
            f.write("-" * 80 + "\n")
            f.write("JSON COMPARISON SUMMARY\n")
            f.write("-" * 80 + "\n\n")
            
            stats = comparator.stats
            f.write(f"Total Fields Compared: {stats['total_fields']}\n")
            f.write(f"Matching Fields: {stats['matching_fields']}\n")
            f.write(f"Different Fields: {stats['different_fields']}\n")
            f.write(f"Missing in Test: {stats['extra_fields']}\n")
            f.write(f"Extra in Test: {stats['missing_fields']}\n")
            f.write(f"Overall Match: {comparator.get_match_percentage():.2f}%\n\n")
            
            if comparator.differences:
                f.write("-" * 80 + "\n")
                f.write("DETAILED DIFFERENCES\n")
                f.write("-" * 80 + "\n\n")
                
                # Group differences by type
                by_type = defaultdict(list)
                for diff in comparator.differences:
                    by_type[diff['type']].append(diff)
                
                for diff_type, diffs in by_type.items():
                    f.write(f"\n{diff_type.upper().replace('_', ' ')} ({len(diffs)} instances):\n")
                    f.write("-" * 40 + "\n")
                    
                    for i, diff in enumerate(diffs[:20], 1):  # Limit to first 20 per type
                        f.write(f"\n{i}. Path: {diff['path']}\n")
                        if 'model_value' in diff:
                            f.write(f"   Model: {diff['model_value'][:200]}...\n" if len(str(diff['model_value'])) > 200 else f"   Model: {diff['model_value']}\n")
                        if 'test_value' in diff:
                            f.write(f"   Test:  {diff['test_value'][:200]}...\n" if len(str(diff['test_value'])) > 200 else f"   Test:  {diff['test_value']}\n")
                        if 'similarity' in diff:
                            f.write(f"   Similarity: {diff['similarity']}%\n")
                    
                    if len(diffs) > 20:
                        f.write(f"\n   ... and {len(diffs) - 20} more\n")
            
            # Image comparison results
            if image_results:
                f.write("\n" + "-" * 80 + "\n")
                f.write("IMAGE COMPARISON SUMMARY\n")
                f.write("-" * 80 + "\n\n")
                
                total_images = len(image_results)
                matching_images = sum(1 for r in image_results if r.get('match', False))
                
                f.write(f"Total Images Compared: {total_images}\n")
                f.write(f"Matching Images: {matching_images}\n")
                f.write(f"Different Images: {total_images - matching_images}\n")
                f.write(f"Match Rate: {(matching_images/total_images*100):.2f}%\n\n")
                
                if any(not r.get('match', False) for r in image_results):
                    f.write("Non-matching or problematic images:\n")
                    for result in image_results:
                        if not result.get('match', False):
                            f.write(f"\n  Model: {result.get('model_image', 'N/A')}\n")
                            f.write(f"  Test:  {result.get('test_image', 'N/A')}\n")
                            f.write(f"  Status: {result.get('status', 'N/A')}\n")
                            if 'similarity' in result:
                                f.write(f"  Similarity: {result['similarity']:.2f}%\n")
    
    def generate_json_report(self, comparator: JSONComparator, 
                            image_results: List[Dict], 
                            output_path: Path):
        """Generate a JSON report for programmatic access."""
        report = {
            'metadata': {
                'timestamp': self.timestamp,
                'model_file': str(self.model_file),
                'test_file': str(self.test_file)
            },
            'json_comparison': {
                'stats': comparator.stats,
                'match_percentage': round(comparator.get_match_percentage(), 2),
                'differences': comparator.differences
            },
            'image_comparison': {
                'total': len(image_results),
                'matching': sum(1 for r in image_results if r.get('match', False)),
                'results': image_results
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)


def find_matching_model_file(test_file: Path, model_dir: Path) -> Path:
    """Find the corresponding model file for a test file."""
    # Try exact name match first
    model_file = model_dir / test_file.name
    if model_file.exists():
        return model_file
    
    # Try matching by base name (without timestamps)
    base_pattern = re.sub(r'_\d{14}', '', test_file.stem)
    for f in model_dir.glob("*.json"):
        if base_pattern in f.stem and f.name.endswith('_with_images.json'):
            return f
    
    raise FileNotFoundError(f"No matching model file found for {test_file.name} in {model_dir}")


def compare_image_folders(model_img_dir: Path, test_img_dir: Path, 
                         model_json: Dict, test_json: Dict) -> List[Dict]:
    """Compare images referenced in both JSONs."""
    if not IMAGE_COMPARISON_AVAILABLE:
        print("Warning: Image comparison libraries not available. Skipping image comparison.")
        print("Install with: pip install Pillow imagehash")
        return []
    
    results = []
    comparator = ImageComparator()
    
    # Extract figure file references from both JSONs
    def extract_figure_files(obj, files=None):
        if files is None:
            files = []
        
        if isinstance(obj, dict):
            if 'Figure_File' in obj:
                files.append(obj['Figure_File'])
            for value in obj.values():
                extract_figure_files(value, files)
        elif isinstance(obj, list):
            for item in obj:
                extract_figure_files(item, files)
        
        return files
    
    model_figures = extract_figure_files(model_json)
    test_figures = extract_figure_files(test_json)
    
    # Compare figures that exist in both
    for i, (model_fig, test_fig) in enumerate(zip(model_figures, test_figures)):
        model_img_path = model_img_dir / model_fig if model_img_dir else None
        test_img_path = test_img_dir / test_fig if test_img_dir else None
        
        if model_img_path and model_img_path.exists() and test_img_path and test_img_path.exists():
            # Try perceptual hash first (faster)
            result = comparator.compare_images_perceptual(model_img_path, test_img_path)
            result['model_image'] = str(model_img_path)
            result['test_image'] = str(test_img_path)
            results.append(result)
        else:
            results.append({
                'model_image': str(model_img_path) if model_img_path else 'N/A',
                'test_image': str(test_img_path) if test_img_path else 'N/A',
                'status': 'file_not_found',
                'match': False
            })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate JSON-based extraction output against model reference',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare a specific test run against model
  python evaluate_extraction.py --test-dir output/JEEMain/backup/Run1 --model-dir output/JEEMain/backup/ModelRun
  
  # Compare with custom output location
  python evaluate_extraction.py --test-dir output/JEEMain/backup/Run2 --model-dir output/JEEMain/backup/ModelRun --output results/eval_run2.txt
  
  # Skip image comparison
  python evaluate_extraction.py --test-dir output/JEEMain/backup/Run3 --model-dir output/JEEMain/backup/ModelRun --no-images
        """
    )
    
    parser.add_argument(
        '--test-dir',
        type=Path,
        required=True,
        help='Directory containing test run output (with *_with_images.json files)'
    )
    
    parser.add_argument(
        '--model-dir',
        type=Path,
        default=Path('output/JEEMain/backup/ModelRun'),
        help='Directory containing model/reference output (default: output/JEEMain/backup/ModelRun)'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        help='Output path for evaluation report (default: auto-generated in test-dir)'
    )
    
    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Skip image comparison'
    )
    
    parser.add_argument(
        '--case-sensitive',
        action='store_true',
        help='Enable case-sensitive text comparison'
    )
    
    parser.add_argument(
        '--strict-whitespace',
        action='store_true',
        help='Do not normalize whitespace in text comparison'
    )
    
    args = parser.parse_args()
    
    # Validate directories
    if not args.test_dir.exists():
        print(f"Error: Test directory not found: {args.test_dir}")
        return 1
    
    if not args.model_dir.exists():
        print(f"Error: Model directory not found: {args.model_dir}")
        return 1
    
    # Find JSON files
    test_files = list(args.test_dir.glob("*_with_images.json"))
    if not test_files:
        print(f"Error: No *_with_images.json files found in {args.test_dir}")
        return 1
    
    print(f"Found {len(test_files)} test file(s) to evaluate")
    print(f"Model directory: {args.model_dir}")
    print(f"Test directory: {args.test_dir}\n")
    
    # Process each test file
    for test_file in test_files:
        print(f"\nEvaluating: {test_file.name}")
        print("=" * 80)
        
        try:
            # Find matching model file
            model_file = find_matching_model_file(test_file, args.model_dir)
            print(f"Model file: {model_file.name}")
            
            # Load JSON files
            with open(model_file, 'r', encoding='utf-8') as f:
                model_json = json.load(f)
            
            with open(test_file, 'r', encoding='utf-8') as f:
                test_json = json.load(f)
            
            # Compare JSON structures
            print("\nComparing JSON structures...")
            comparator = JSONComparator(
                ignore_whitespace=not args.strict_whitespace,
                case_sensitive=args.case_sensitive
            )
            comparator.compare_dicts(model_json, test_json)
            
            print(f"  Match percentage: {comparator.get_match_percentage():.2f}%")
            print(f"  Total differences: {len(comparator.differences)}")
            
            # Compare images if requested
            image_results = []
            if not args.no_images:
                print("\nComparing images...")
                # Determine image directories
                model_img_dir = args.model_dir  # Old structure: images in same dir
                test_img_dir = args.test_dir / "images"  # New structure: images in subdir
                
                if not test_img_dir.exists():
                    test_img_dir = args.test_dir  # Fallback to same dir
                
                image_results = compare_image_folders(
                    model_img_dir, test_img_dir, 
                    model_json, test_json
                )
                
                if image_results:
                    matching = sum(1 for r in image_results if r.get('match', False))
                    print(f"  Images compared: {len(image_results)}")
                    print(f"  Matching: {matching}")
                    print(f"  Different: {len(image_results) - matching}")
            
            # Generate reports
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_gen = EvaluationReport(model_file, test_file)
            
            if args.output:
                txt_output = args.output
                json_output = args.output.with_suffix('.json')
            else:
                base_name = f"evaluation_{test_file.stem}_{timestamp}"
                txt_output = args.test_dir / f"{base_name}.txt"
                json_output = args.test_dir / f"{base_name}.json"
            
            print(f"\nGenerating reports...")
            report_gen.generate_text_report(comparator, image_results, txt_output)
            report_gen.generate_json_report(comparator, image_results, json_output)
            
            print(f"  Text report: {txt_output}")
            print(f"  JSON report: {json_output}")
            
            # Print summary
            print("\n" + "=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Overall Match: {comparator.get_match_percentage():.2f}%")
            if image_results:
                img_match = sum(1 for r in image_results if r.get('match', False)) / len(image_results) * 100
                print(f"Image Match: {img_match:.2f}%")
            
        except Exception as e:
            print(f"Error processing {test_file.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "=" * 80)
    print("Evaluation complete!")
    return 0


if __name__ == "__main__":
    exit(main())
