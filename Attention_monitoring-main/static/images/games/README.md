# Game Thumbnails

## How to Add Your Own Thumbnail Images

To display custom thumbnails for the games, follow these steps:

### 1. Add Image Files

Place your thumbnail images in this folder (`static/images/games/`) with these exact names:

- `candy-riddles.jpg` or `candy-riddles.png`
- `block-puzzle.jpg` or `block-puzzle.png`
- `merge-cakes.jpg` or `merge-cakes.png`
- `2048.jpg` or `2048.png`
- `word-search.jpg` or `word-search.png`
- `helix-jump.jpg` or `helix-jump.png`

### 2. Recommended Image Specifications

- **Dimensions**: 300px × 150px (or any 2:1 aspect ratio)
- **Format**: JPG or PNG
- **Size**: Keep under 200KB for fast loading
- **Quality**: Medium to high quality

### 3. Where to Get Images

You can:

- Take screenshots from the games themselves
- Create custom thumbnails with Canva or Photoshop
- Search for game images online (ensure you have rights to use them)
- Use AI image generators like DALL-E or Midjourney

### 4. Current Status

The app will automatically use your images once you place them in this folder.
If no image is found, it will show a colorful gradient placeholder with the game name.

### Example File Structure:

```
static/
  images/
    games/
      candy-riddles.png
      block-puzzle.png
      merge-cakes.png
      2048.png
      word-search.png
      helix-jump.png
```

That's it! The thumbnails will appear automatically in the games modal.
