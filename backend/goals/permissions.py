from rest_framework.permissions import BasePermission

OWNER_ONLY_ACTIONS = {"update", "partial_update", "destroy", "invite", "cancel_invite", "remove_member"}


class IsGoalOwnerForManagement(BasePermission):
    """Qualquer participante lê e guarda dinheiro; só o dono edita, exclui,
    convida ou remove pessoas."""

    message = "Somente o dono da meta pode fazer isso."

    def has_object_permission(self, request, view, obj) -> bool:
        if getattr(view, "action", None) in OWNER_ONLY_ACTIONS:
            return obj.owner_id == request.user.id
        return True
