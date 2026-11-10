from rest_framework.routers import DefaultRouter

from .views import GoalViewSet, MyInviteViewSet

router = DefaultRouter()
router.register("goals", GoalViewSet, basename="goal")
router.register("invites", MyInviteViewSet, basename="invite")

urlpatterns = router.urls
