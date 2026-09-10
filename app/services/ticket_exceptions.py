"""Excepciones de dominio compartidas por los casos de uso de tickets.

Los services expresan errores del negocio con estas clases. La capa HTTP es
la responsable de convertirlas luego en respuestas 400, 403 o 404.
"""


class TicketServiceError(Exception):
    pass


class TicketNotFoundError(TicketServiceError):
    pass


class AssignedUserNotFoundError(TicketServiceError):
    pass


class TicketPermissionError(TicketServiceError):
    pass


class InvalidStatusTransitionError(TicketServiceError):
    pass


class TicketAlreadyAssignedError(TicketServiceError):
    pass


class TicketClaimNotAllowedError(TicketServiceError):
    pass


class MissingStatusChangeReasonError(TicketServiceError):
    pass


class TicketTeamAssignmentError(TicketServiceError):
    pass


class TicketTeamNotFoundError(TicketServiceError):
    pass


class TicketTeamPermissionError(TicketServiceError):
    pass


class InvalidAssignedUserError(TicketServiceError):
    pass


class TicketCategoryNotFoundError(TicketServiceError):
    pass


class InvalidTicketCategoryError(TicketServiceError):
    pass


class InvalidTicketCategoryChangeError(TicketServiceError):
    pass


class MissingCategoryChangeReasonError(TicketServiceError):
    pass


class TicketDependencyError(TicketServiceError):
    pass


class TicketDependencyNotFoundError(TicketServiceError):
    pass


class TicketBlockedByOpenDependenciesError(TicketServiceError):
    pass


class TicketArchiveError(TicketServiceError):
    pass


class TicketCommentError(TicketServiceError):
    pass


class TicketCommentNotAllowedError(TicketCommentError):
    pass
