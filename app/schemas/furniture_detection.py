"""
example of detected objects in furniture detection API response.
detected_objects = {
  "detectionId": "det-uuid",
  "imageSize": {
    "width": 1920,
    "height": 1080
  },
  "objects": [
    {
      "objectId": "obj-uuid",
      "label": "office chair",
      "confidence": 0.7,
      "confidenceSource": "NOT_PROVIDED",
      "bbox": [120, 80, 420, 650],
      "selected": False
    }
  ]
}
"""