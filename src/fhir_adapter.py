"""FHIR R4-style Bundle -> normalized ClaimGuard claim envelope.

Maps ONLY what the bundle actually carries (docs/11_FHIR_Orientation.md's
mapping table). Fields FHIR does not carry stay null / empty and are listed in
NOT_CARRIED_BY_FHIR so a downstream rule sees "unknown" (-> UNABLE_TO_ASSESS)
instead of a silently invented value. Nothing here reads the normalized
claims file: this is a real adapter, not a lookup.

Resource references are resolved against the bundle's fullUrl values. A
reference that does not resolve is still reduced to its trailing id (so a
dangling reference stays visible to the rules) but is reported as a warning.
Attachment text is decoded and kept as untrusted data.

Educational subset, not a conformant HL7 FHIR implementation: no terminology
validation, no profile checks, one Claim per Bundle.
"""
import base64
import re

SCHEMA_VERSION = '1.0.0'
# The transport envelope requires a non-empty `notes` string, but FHIR carries none.
# An explicit marker keeps that visible instead of inventing free text.
NOTES_PLACEHOLDER = '[notes not carried by FHIR bundle]'

# Normalized fields the FHIR projection cannot supply (docs/11 "Deliberate limitations").
NOT_CARRIED_BY_FHIR = [
    'authorizations[].patient_id', 'authorizations[].service_code', 'authorizations[].status',
    'authorizations[].valid_from', 'authorizations[].valid_to', 'authorizations[].max_quantity',
    'notes',
]
# Fields derived by a rule of the adapter rather than read from a dedicated element.
INFERRED = {
    'lines[].line_id': 'L<Claim.item.sequence>',
    'attachments[].service_code': 'parsed from DocumentReference.description ("Synthetic <SERVICE-CODE>")',
    'attachments[].document_status': 'DocumentReference.docStatus (preliminary -> draft)',
    'attachments[].service_date': 'DocumentReference.context.period.start',
    'coverage.member_id': 'Coverage.subscriberId',
    'policy_id': 'Coverage.class[type=plan].value',
}
DOC_STATUS = {'preliminary': 'draft', 'final': 'final'}


class FhirMappingError(ValueError):
    """The bundle cannot be mapped to a schema-valid envelope at all; the caller
    quarantines it rather than guessing."""


def _last_segment(ref):
    return ref.rsplit('/', 1)[-1]


def _first_code(codeable):
    for c in (codeable or {}).get('coding', []):
        if c.get('code'):
            return c['code']
    return None


def _ident(resource, suffix):
    for i in resource.get('identifier', []):
        if (i.get('system') or '').endswith(suffix):
            return i.get('value')
    return None


class _Bundle:
    def __init__(self, bundle):
        if bundle.get('resourceType') != 'Bundle':
            raise FhirMappingError('Not a FHIR Bundle')
        self.by_url = {}
        self.by_type = {}
        for e in bundle.get('entry', []):
            r = e.get('resource') or {}
            if e.get('fullUrl'):
                self.by_url[e['fullUrl']] = r
            self.by_type.setdefault(r.get('resourceType'), []).append(r)
        self.warnings = []

    def resolve(self, reference_obj, what):
        """Return (resource_or_None, id). Never guesses beyond the trailing id."""
        ref = (reference_obj or {}).get('reference')
        if not ref:
            return None, None
        res = self.by_url.get(ref)
        if res is None:
            self.warnings.append(f'unresolved_reference: {what} -> {ref}')
            return None, _last_segment(ref)
        return res, res.get('id')


def bundle_to_claim(bundle):
    """Return (claim_envelope, report). Raises FhirMappingError if a field the
    envelope requires cannot be derived at all."""
    b = _Bundle(bundle)
    claims = b.by_type.get('Claim', [])
    if len(claims) != 1:
        raise FhirMappingError(f'Expected exactly one Claim, found {len(claims)}')
    cl = claims[0]
    if not cl.get('id'):
        raise FhirMappingError('Claim.id missing')

    patient, patient_id = b.resolve(cl.get('patient'), 'Claim.patient')
    member_id = _ident(patient, '/member') if patient else None
    _, provider_id = b.resolve(cl.get('provider'), 'Claim.provider')
    _, payer_id = b.resolve(cl.get('insurer'), 'Claim.insurer')

    insurance = (cl.get('insurance') or [{}])
    cov_res, _ = b.resolve(insurance[0].get('coverage'), 'Claim.insurance.coverage')
    if cov_res is None:
        raise FhirMappingError('Claim.insurance.coverage does not resolve to a Coverage in the bundle')
    policy_id = next((c.get('value') for c in cov_res.get('class', [])
                      if _first_code(c.get('type')) == 'plan'), None)
    _, beneficiary_id = b.resolve(cov_res.get('beneficiary'), 'Coverage.beneficiary')
    period = cov_res.get('period') or {}
    coverage = {
        'coverage_id': cov_res.get('id'), 'status': cov_res.get('status'),
        'beneficiary_patient_id': beneficiary_id, 'member_id': cov_res.get('subscriberId'),
        'start_date': period.get('start'), 'end_date': period.get('end'),
    }

    lines, auth_ids = [], []
    currency_seen = None
    for pos, it in enumerate(cl.get('item', []), start=1):
        auth = next((e.get('valueString') for e in it.get('extension', [])
                     if (e.get('url') or '').endswith('line-authorization-id')), None)
        if auth and auth not in auth_ids:
            auth_ids.append(auth)
        currency_seen = currency_seen or (it.get('unitPrice') or {}).get('currency')
        lines.append({
            'line_id': f"L{it.get('sequence', pos)}",
            'service_code': _first_code(it.get('productOrService')),
            'service_date': it.get('servicedDate'),
            'modifier': _first_code((it.get('modifier') or [None])[0]),
            'quantity': (it.get('quantity') or {}).get('value'),
            'unit_price': (it.get('unitPrice') or {}).get('value'),
            'net_amount': (it.get('net') or {}).get('value'),
            'authorization_id': auth,
        })
    for ins in insurance:
        for a in ins.get('preAuthRef', []):
            if a not in auth_ids:
                auth_ids.append(a)
    authorizations = [{'authorization_id': a, 'patient_id': None, 'service_code': None, 'status': None,
                       'valid_from': None, 'valid_to': None, 'max_quantity': None} for a in auth_ids]

    attachments = []
    for doc in b.by_type.get('DocumentReference', []):
        _, doc_patient = b.resolve(doc.get('subject'), 'DocumentReference.subject')
        raw = ((doc.get('content') or [{}])[0].get('attachment') or {}).get('data')
        try:
            text = base64.b64decode(raw, validate=True).decode('utf-8') if raw else ''
        except (ValueError, UnicodeDecodeError):
            text = ''
            b.warnings.append(f"undecodable_attachment: {doc.get('id')}")
        m = re.fullmatch(r'Synthetic (SVC-[A-Z0-9-]+)', doc.get('description') or '')
        doc_status = doc.get('docStatus')
        if doc_status not in DOC_STATUS:
            b.warnings.append(f"unknown_docStatus: {doc.get('id')} = {doc_status!r}")
        attachments.append({
            'attachment_id': doc.get('id'), 'type': _first_code(doc.get('type')) or '',
            'patient_id': doc_patient or '',
            'service_code': m.group(1) if m else '',
            'service_date': ((doc.get('context') or {}).get('period') or {}).get('start') or '',
            'document_status': DOC_STATUS.get(doc_status, doc_status or ''),
            'text': text,
        })
    linked = {_last_segment(s['valueReference']['reference']) for s in cl.get('supportingInfo', [])
              if (s.get('valueReference') or {}).get('reference')}
    have = {a['attachment_id'] for a in attachments}
    for missing in sorted(linked - have):
        b.warnings.append(f'unresolved_reference: Claim.supportingInfo -> {missing} (no DocumentReference in bundle)')

    total = cl.get('total') or {}
    currency = total.get('currency') or currency_seen
    for name, value in (('patient', patient_id), ('provider', provider_id), ('payer', payer_id),
                        ('policy', policy_id), ('currency', currency), ('submission date', cl.get('created'))):
        if not value:
            raise FhirMappingError(f'Cannot derive required field: {name}')

    claim = {
        'schema_version': SCHEMA_VERSION, 'claim_id': cl['id'],
        'invoice_number': _ident(cl, '/invoice'), 'patient_id': patient_id, 'member_id': member_id,
        'provider_id': provider_id, 'payer_id': payer_id, 'policy_id': policy_id,
        'diagnosis_code': _first_code(((cl.get('diagnosis') or [{}])[0]).get('diagnosisCodeableConcept')),
        'submission_date': cl.get('created'), 'currency': currency, 'total_amount': total.get('value'),
        'coverage': coverage, 'lines': lines, 'authorizations': authorizations,
        'attachments': attachments, 'notes': NOTES_PLACEHOLDER,
    }
    report = {
        'source_format': 'fhir_bundle', 'claim_id': cl['id'],
        'not_carried_by_fhir': list(NOT_CARRIED_BY_FHIR), 'inferred': dict(INFERRED),
        'warnings': b.warnings,
    }
    return claim, report
