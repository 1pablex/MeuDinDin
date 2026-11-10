from rest_framework import serializers

from .models import Category, Transaction


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind", "color"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o nome.")
        return value

    def validate_color(self, value: str) -> str:
        import re

        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise serializers.ValidationError("Use uma cor no formato #RRGGBB.")
        return value.upper()

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        name = attrs.get("name", getattr(self.instance, "name", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        qs = Category.objects.filter(user=user, name__iexact=name, kind=kind)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": "Você já tem uma categoria com esse nome."})
        return attrs


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    category_color = serializers.CharField(source="category.color", read_only=True, default=None)
    is_occurrence = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "description", "amount", "category", "category_name", "category_color",
            "date", "recurrence", "is_occurrence", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_is_occurrence(self, obj: Transaction) -> bool:
        return obj.parent_id is not None

    def validate_description(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe a descrição.")
        return value

    def validate_category(self, value: Category | None) -> Category | None:
        # Impede usar categoria de outro usuário (IDOR)
        if value is not None and value.user_id != self.context["request"].user.id:
            raise serializers.ValidationError("Categoria inválida.")
        return value

    def validate(self, attrs: dict) -> dict:
        category = attrs.get("category", getattr(self.instance, "category", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if category is not None and category.kind != kind:
            raise serializers.ValidationError({"category": "A categoria não corresponde ao tipo do lançamento."})
        if self.instance is not None and self.instance.parent_id and attrs.get("recurrence", "none") != "none":
            raise serializers.ValidationError({"recurrence": "Ocorrências geradas não podem ser recorrentes."})
        return attrs
