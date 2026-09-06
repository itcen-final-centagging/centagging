"""SKU 카탈로그 메타데이터 스펙의 무결성을 검증합니다."""

import unittest

from app.core import catalog_spec


class VisualVerifiabilityTest(unittest.TestCase):
    """XAI 비교 대상 속성 분류가 빠짐없이 등록됐는지 검증합니다."""

    def test_every_common_attribute_is_classified(self) -> None:
        """공통 속성은 모두 시각 판별 여부가 등록돼 있어야 합니다."""
        missing = set(catalog_spec.COMMON_ATTRIBUTE) - set(
            catalog_spec.COMMON_ATTRIBUTE_VISUALLY_VERIFIABLE
        )

        self.assertEqual(missing, set(), f"공통 속성 분류 누락: {missing}")

    def test_every_category_attribute_is_classified(self) -> None:
        """카테고리별 속성도 모두 시각 판별 여부가 등록돼 있어야 합니다.

        등록을 빠뜨리면 visual_attribute_names()가 조용히 제외해 버려서
        비교 항목이 사라진 것을 아무도 알아채지 못합니다.
        """
        for category, attributes in catalog_spec.PRODUCT_ATTRIBUTE.items():
            with self.subTest(category=category):
                classified = (
                    catalog_spec.PRODUCT_ATTRIBUTE_VISUALLY_VERIFIABLE.get(
                        category, {}
                    )
                )
                missing = set(attributes) - set(classified)

                self.assertEqual(
                    missing,
                    set(),
                    f"'{category}' 속성 분류 누락: {missing}",
                )

    def test_no_stale_classification_keys(self) -> None:
        """스펙에서 사라진 속성이 분류표에 남아 있지 않아야 합니다."""
        for category, classified in (
            catalog_spec.PRODUCT_ATTRIBUTE_VISUALLY_VERIFIABLE.items()
        ):
            with self.subTest(category=category):
                attributes = catalog_spec.PRODUCT_ATTRIBUTE.get(category, {})
                stale = set(classified) - set(attributes)

                self.assertEqual(
                    stale,
                    set(),
                    f"'{category}'에 정의되지 않은 분류: {stale}",
                )

    def test_visual_attribute_names_is_subset_of_attribute_names(self) -> None:
        """비교 대상은 전체 속성의 부분집합이며 순서를 유지합니다."""
        for category in catalog_spec.CATEGORIES:
            with self.subTest(category=category):
                names = catalog_spec.attribute_names(category)
                visual = catalog_spec.visual_attribute_names(category)

                self.assertTrue(set(visual).issubset(set(names)))
                self.assertEqual(
                    visual,
                    [name for name in names if name in set(visual)],
                )

    def test_excludes_attributes_that_images_cannot_show(self) -> None:
        """이미지로 확인할 수 없는 속성은 비교 대상에서 빠집니다."""
        self.assertNotIn(
            "size", catalog_spec.visual_attribute_names("침대")
        )
        self.assertNotIn(
            "firmness", catalog_spec.visual_attribute_names("매트리스")
        )
        for category in catalog_spec.CATEGORIES:
            with self.subTest(category=category):
                visual = catalog_spec.visual_attribute_names(category)
                self.assertNotIn("brand", visual)
                self.assertNotIn("selling_price", visual)

    def test_every_category_has_comparable_attributes(self) -> None:
        """모든 카테고리에 비교 가능한 속성이 최소 하나는 있어야 합니다."""
        for category in catalog_spec.CATEGORIES:
            with self.subTest(category=category):
                self.assertTrue(
                    catalog_spec.visual_attribute_names(category),
                    f"'{category}'에 비교 가능한 속성이 없습니다.",
                )

    def test_unknown_category_raises(self) -> None:
        """정의되지 않은 대분류는 오류로 알립니다."""
        with self.assertRaises(KeyError):
            catalog_spec.visual_attribute_names("정의되지 않은 카테고리")


if __name__ == "__main__":
    unittest.main()
