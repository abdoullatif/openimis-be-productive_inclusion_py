from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import HistoryModel


class SereSettings(models.Model):
    """
    Paramétrage singleton (Django Admin) pour l'éligibilité SERE / subvention.
    """

    presence_count_min = models.PositiveIntegerField(
        default=8,
        verbose_name=_('Présences minimum (inclus)'),
        help_text=_(
            'Seuil bas : les membres avec un nombre de présences strictement inférieur '
            'passent en statut INACTIVE.'
        ),
    )
    presence_count_max = models.PositiveIntegerField(
        default=10,
        verbose_name=_('Présences maximum (inclus)'),
        help_text=_(
            'Seuil haut : les membres avec un nombre de présences entre min et max (inclus) '
            'passent en statut ACTIVE. Au-delà du max → INACTIVE.'
        ),
    )
    benefit_plan = models.ForeignKey(
        'social_protection.BenefitPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_('Programme social protection (référence)'),
        help_text=_(
            'Programme utilisé pour mapper les membres SERE (via code_ménage) aux bénéficiaires. '
            'Les membres INACTIVE seront suspendus sur ce programme (exclus des paiements).'
        ),
    )
    sync_social_protection = models.BooleanField(
        default=True,
        verbose_name=_('Appliquer SP à la complétion de la tâche subvention'),
        help_text=_(
            'Si coché : à la validation de la tâche subvention, INACTIVE → SUSPENDED '
            'et ACTIVE → ACTIVE sur le régime (hors GRADUATED). Aucune sync SP à l\'import.'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Paramétrage SERE / subvention')
        verbose_name_plural = _('Paramétrage SERE / subvention')

    def __str__(self):
        plan = self.benefit_plan
        plan_label = f'{plan.code} — {plan.name}' if plan else _('aucun programme')
        return _(
            'Présences [%(min)s–%(max)s] · Programme: %(plan)s'
        ) % {
            'min': self.presence_count_min,
            'max': self.presence_count_max,
            'plan': plan_label,
        }

    def clean(self):
        if self.presence_count_min is not None and self.presence_count_max is not None:
            if self.presence_count_min > self.presence_count_max:
                raise ValidationError({
                    'presence_count_min': _(
                        'Le minimum ne peut pas être supérieur au maximum.'
                    ),
                })

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Singleton : interdire la suppression.
        pass

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'presence_count_min': 8,
                'presence_count_max': 10,
                'sync_social_protection': True,
            },
        )
        return obj


class SerePresenceThresholdSettings(SereSettings):
    """Proxy admin : seuils de présence uniquement."""

    class Meta:
        proxy = True
        verbose_name = _('Seuils de présence SERE')
        verbose_name_plural = _('Seuils de présence SERE')


class SereSocialProtectionMappingSettings(SereSettings):
    """Proxy admin : mapping régime social protection."""

    class Meta:
        proxy = True
        verbose_name = _('Mapping régime social protection')
        verbose_name_plural = _('Mapping régime social protection')


class SereSubsidyBatch(HistoryModel):
    """Lot de validation des présences / subvention (entité de la tâche)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('En attente')
        APPLIED = 'APPLIED', _('Appliqué')
        FAILED = 'FAILED', _('Échoué')

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    benefit_plan = models.ForeignKey(
        'social_protection.BenefitPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    active_count = models.PositiveIntegerField(default=0)
    inactive_count = models.PositiveIntegerField(default=0)
    members_total = models.PositiveIntegerField(default=0)
    summary = models.JSONField(blank=True, default=dict)
    task_id = models.UUIDField(blank=True, null=True)

    class Meta:
        verbose_name = _('Lot validation subvention SERE')
        verbose_name_plural = _('Lots validation subvention SERE')
        ordering = ('-date_created',)

    def __str__(self):
        return f'Subvention {self.pk} ({self.status})'


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
    presence_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Nombre de présences'),
        help_text=_(
            'Compteur de présences (import Excel / saisie). '
            'Utilisé pour le statut SERE selon les seuils admin.'
        ),
    )

    class Meta:
        verbose_name = _('Membre SERE')
        verbose_name_plural = _('Membres SERE')
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return f'{self.last_name} {self.first_name or ""}'.strip()


class SereMemberPresence(HistoryModel):
    """
    Détail optionnel par date (non utilisé par l'import Excel).
    La source de vérité opérationnelle est SereMember.presence_count.
    """
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
