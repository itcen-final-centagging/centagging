from PIL import Image

def get_crop_image(image: Image.Image, bbox) -> Image.Image:
    ymin, xmin, ymax, xmax = bbox

    left = round(xmin / 1000 * image.width)
    right = round(xmax / 1000 * image.width)
    upper = round(ymin / 1000 * image.height)
    lower = round(ymax / 1000 * image.height)

    return image.crop((left, upper, right, lower))