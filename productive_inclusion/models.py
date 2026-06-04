from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import HistoryModel


class SereGroup(HistoryModel):
    import_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    locality = models.CharField(max_length=255, blank=True, null=True)
    location = models.ForeignKey(
        'location.Location',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sere_groups',
    )

    class Meta:
        verbose_name = _('Groupement SERE')
        verbose_name_plural = _('Groupements SERE')
        ordering = ('name',)

    def __str__(self):
        return self.name


class SereMember(HistoryModel):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Actif')
        INACTIVE = 'INACTIVE', _('Inactif')
        PENDING = 'PENDING', _('En attente')
        SUSPENDED = 'SUSPENDED', _('Suspendu')

    group = models.ForeignKey(
        SereGroup,
        on_delete=models.CASCADE,
        related_name='members',
    )
    last_name = models.CharField(max_length=255)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    role = models.CharField(max_length=128, blank=True, null=True)
    beneficiary_type = models.CharField(max_length=128, blank=True, null=True)
    code_menage = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        verbose_name = _('Membre SERE')
        verbose_name_plural = _('Membres SERE')
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return f'{self.last_name} {self.first_name or ""}'.strip()


class SereMemberPresence(HistoryModel):
    """Pointage de présence d'un membre (une ligne par date de présence)."""
    member = models.ForeignKey(
        SereMember,
        on_delete=models.CASCADE,
        related_name='presences',
    )
    presence_date = models.DateField()

    class Meta:
        verbose_name = _('Présence membre SERE')
        verbose_name_plural = _('Présences membres SERE')
        ordering = ('-presence_date',)
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'presence_date'],
                condition=models.Q(is_deleted=False),
                name='pi_sere_member_presence_member_date_unique',
            ),
        ]

    def __str__(self):
        return f'{self.member_id} @ {self.presence_date}'


class SereActivity(HistoryModel):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', _('Planifiée')
        IN_PROGRESS = 'IN_PROGRESS', _('En cours')
        COMPLETED = 'COMPLETED', _('Terminée')
        CANCELLED = 'CANCELLED', _('Annulée')

    group = models.ForeignKey(
        SereGroup,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    activity_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        verbose_name = _('Activité SERE')
        verbose_name_plural = _('Activités SERE')
        ordering = ('-activity_date', 'title')

    def __str__(self):
        return self.title
