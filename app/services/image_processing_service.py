from PIL import Image

def get_crop_image(image: Image.Image, bbox) -> Image.Image:
    left = round(bbox["xmin"] / 1000 * image.width)
    right = round(bbox["xmax"] / 1000 * image.width)
    upper = round(bbox["ymax"] / 1000 * image.height)
    lower = round(bbox["ymin"] / 1000 * image.height)

    return image.crop((left, upper, right, lower))