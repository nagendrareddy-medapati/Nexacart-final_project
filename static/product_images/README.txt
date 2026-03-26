# Product Images Folder

## Structure
Each product gets its OWN folder named by product ID:
  product_images/
    1/          ← Product ID 1
      1.jpg     ← Main image (shown first)
      2.jpg     ← Second angle
      3.jpg     ← Third angle  
      4.jpg     ← Fourth angle / detail shot
    2/
      1.jpg
      2.jpg
      ... etc

## Rules
- Folder name = product ID (find IDs in admin panel at /admin/products)
- Image names: 1.jpg, 2.jpg, 3.jpg, 4.jpg  (or .png, .jpeg)
- 1.jpg is always the MAIN image shown on product cards and listings
- If a numbered image doesn't exist, the system skips it
- If folder doesn't exist, a placeholder gradient is shown
- Minimum: just 1.jpg is fine. Maximum: 4 images.

## Supported formats
.jpg, .jpeg, .png

## Recommended size
- Minimum: 400x400 pixels
- Recommended: 800x800 pixels (square)
- Max file size: 500KB per image (compress before uploading)

## Example
To set images for the iPhone 15 (product ID = 1):
  1. Create folder:  product_images/1/
  2. Add images:     1.jpg (front), 2.jpg (back), 3.jpg (side), 4.jpg (box)

## That's it! No code changes needed.
