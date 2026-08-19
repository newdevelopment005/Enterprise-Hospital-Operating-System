// Client-side validation mirroring the patient-service DTO rules.
// Returns a list of field errors; empty list = valid.

import type { RegisterPatient } from './types'

const NID_RE = /^(\d{3}-\d{6}-\d|\d{8,16})$/
const PASSPORT_RE = /^[A-Z]{1,2}\d{7}$/
const PHONE_RE = /^\+?\d{8,15}$/
const CARD_RE = /^[A-Z0-9-]{6,20}$/

export function validatePhone(phone?: string): boolean {
  return phone ? PHONE_RE.test(phone) : true
}

export function validateRegister(p: RegisterPatient): string[] {
  const errors: string[] = []

  if (p.first_name.trim().length < 1) errors.push('First name is required')
  if (p.last_name.trim().length < 1) errors.push('Last name is required')
  if (/\d/.test(p.first_name) || /\d/.test(p.last_name)) errors.push('Names must not contain digits')

  if (p.date_of_birth) {
    const dob = new Date(p.date_of_birth)
    const today = new Date()
    if (Number.isNaN(dob.getTime())) errors.push('Invalid date of birth')
    else if (dob > today) errors.push('Date of birth cannot be in the future')
    else if (dob.getFullYear() < 1900) errors.push('Date of birth is unreasonably old')
  }

  if (p.national_identifier) {
    const cleaned = p.national_identifier.replace(/\s+/g, '')
    if (!NID_RE.test(cleaned)) errors.push('Invalid National ID format')
  }

  for (const ident of p.identifiers ?? []) {
    if (ident.identifier_type === 'PASSPORT' && !PASSPORT_RE.test(ident.identifier_value.toUpperCase())) {
      errors.push(`Invalid passport format for ${ident.identifier_value}`)
    }
  }

  const contacts = [p.emergency_contact, ...(p.contacts ?? [])].filter(
    (c): c is NonNullable<typeof p.emergency_contact> => Boolean(c),
  )
  for (const contact of contacts) {
    if (!PHONE_RE.test(contact.phone)) errors.push(`Invalid phone: ${contact.phone}`)
    if (!contact.name.trim()) errors.push('Emergency contact name is required')
  }

  const insurance = p.insurance
  if (insurance?.card_number && !CARD_RE.test(insurance.card_number)) {
    errors.push('Invalid insurance card number')
  }
  if (insurance?.policy_number && !CARD_RE.test(insurance.policy_number)) {
    errors.push('Invalid insurance policy number')
  }

  return [...new Set(errors)]
}

export function validateSearchQuery(q: string): string | null {
  if (q.length > 255) return 'Search is too long'
  return null
}