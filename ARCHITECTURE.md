# ARCHITECTURE.md

# Enterprise Hospital Operating System (EHOS)

**Version:** 1.0.0  
**Document Type:** Enterprise Architecture  
**Audience:** Software Architects, Backend Developers, DevOps Engineers, AI Engineers

---

# 1. Purpose

This document defines the technical architecture of the Enterprise Hospital Operating System (EHOS).

It establishes:

- System architecture
- Service boundaries
- Communication patterns
- Data ownership
- Security zones
- AI architecture
- Infrastructure
- Scalability strategy

Every service must follow this architecture.

---

# 2. Architecture Philosophy

EHOS follows these architectural principles:

- Domain-Driven Design (DDD)
- Microservices Architecture
- Event-Driven Architecture (EDA)
- API-First Development
- Offline-First Design
- AI-Native Platform
- Zero Trust Security
- Cloud-Optional Deployment
- Infrastructure as Code (IaC)

---

# 3. High-Level Architecture

```text
                        Users
                           │
      ┌───────────────────────────────────┐
      │  Web Portal / Mobile / Kiosk      │
      └───────────────────────────────────┘
                           │
                    API Gateway
                           │
                Authentication Service
                           │
     ┌─────────────────────────────────────────────┐
     │             Microservices Layer             │
     ├─────────────────────────────────────────────┤
     │ Patient │ EHR │ Pharmacy │ Lab │ Radiology │
     │ Billing │ HR  │ Finance  │ Inventory       │
     │ Surgery │ ICU │ Emergency│ AI Gateway      │
     └─────────────────────────────────────────────┘
                           │
                    Apache Kafka
                           │
      ┌──────────────────────────────────────────┐
      │ PostgreSQL │ Redis │ MinIO │ Vector DB   │
      └──────────────────────────────────────────┘
                           │
                  Monitoring & Security
```

---

# 4. Architectural Layers

## Presentation Layer

Responsible for user interaction.

Components:

- React Web Portal
- Flutter Mobile App
- Patient Portal
- Staff Portal
- Executive Dashboard
- Self-Service Kiosks

---

## API Layer

Responsibilities:

- Authentication
- Authorization
- API Routing
- Rate Limiting
- API Versioning
- Request Validation
- Response Standardization

Recommended:

- Kong
- Envoy
- NGINX

---

## Business Layer

Contains all domain microservices.

Each service owns:

- Business logic
- Database
- Events
- APIs

Never access another service's database directly.

---

## Event Layer

Apache Kafka acts as the central nervous system.

Examples:

PatientRegistered

↓

Patient Service

↓

Kafka Topic

↓

Billing Service

↓

EHR Service

↓

Notification Service

↓

Analytics

---

## Data Layer

Each microservice owns its own database schema.

Primary Database:

PostgreSQL

Caching:

Redis

Object Storage:

MinIO

AI Knowledge:

Qdrant

---

# 5. Microservice Catalog

## Clinical

Patient Service

Appointment Service

Triage Service

Emergency Service

EHR Service

Pharmacy Service

Laboratory Service

Radiology Service

Surgery Service

ICU Service

Bed Management Service

Telemedicine Service

---

## Administrative

HR Service

Payroll Service

Finance Service

Billing Service

Insurance Service

Inventory Service

Procurement Service

Vendor Service

Asset Service

---

## AI

HospitalGPT

Prompt Service

Embedding Service

Model Service

Inference Service

OCR Service

Speech Service

Knowledge Service

Analytics Service

Executive AI Service

---

## Platform

Authentication

Notification

Audit

File Storage

Search

Reporting

Configuration

Feature Flags

---

# 6. Communication Patterns

## Synchronous

REST API

Use for:

Queries

Authentication

Search

Configuration

User interaction

---

## Asynchronous

Apache Kafka

Use for:

Billing

Inventory

Notifications

Analytics

AI

Auditing

Forecasting

Long-running workflows

---

# 7. Example Event Flow

Medication Dispensed

↓

Pharmacy Service

↓

MedicationDispensed Event

↓

Inventory Service

↓

Billing Service

↓

Patient Timeline

↓

Analytics

↓

Executive Dashboard

---

# 8. Service Ownership

Each service owns:

Business Logic

API

Database

Events

Validation

Security

Testing

Documentation

No shared business logic across unrelated services.

---

# 9. AI Architecture

```
                    HospitalGPT
                         │
                AI Gateway Service
                         │
        ┌────────────────────────────────┐
        │ Prompt Manager                 │
        │ Model Manager                  │
        │ Memory Manager                 │
        │ Embedding Engine               │
        │ Vector Database                │
        │ Knowledge Base                 │
        └────────────────────────────────┘
                         │
             Local LLM Inference Engine
                         │
       Llama / Qwen / Gemma / Mistral
```

Everything runs locally.

No patient data leaves the hospital.

---

# 10. Data Ownership

Patient Service

owns:

Patient

Identity

Contacts

Emergency Contacts

Insurance

---

EHR Service

owns:

Vitals

Diagnoses

Medications

Clinical Notes

SOAP Notes

Progress Notes

---

Billing Service

owns:

Invoices

Payments

Claims

Receipts

Taxes

---

Inventory Service

owns:

Products

Lots

Expiry

Suppliers

Warehouses

Stock

---

# 11. Security Zones

Zone 1

Public Access

Patient Portal

---

Zone 2

Staff Applications

Clinical Portal

---

Zone 3

Core Services

Microservices

---

Zone 4

Database Layer

PostgreSQL

Redis

Vector DB

---

Zone 5

Infrastructure

Kubernetes

Monitoring

Secrets

Backups

---

# 12. Infrastructure

Compute

Kubernetes

Docker

GPU Nodes

---

Networking

NGINX

HAProxy

Service Mesh (optional)

---

Storage

PostgreSQL

Redis

MinIO

Qdrant

---

Monitoring

Prometheus

Grafana

Loki

Tempo

Alertmanager

---

# 13. Scalability Strategy

Scale Horizontally

Stateless Services

Database Replication

Kafka Partitions

Redis Cluster

Multiple AI Nodes

GPU Pool

Load Balancers

---

# 14. Disaster Recovery

Nightly Backups

Incremental Backups

Point-in-Time Recovery

Off-site Backup (optional)

Failover Cluster

Database Replication

Regular Recovery Testing

---

# 15. Observability

Every service must expose:

Health Check

Readiness Check

Liveness Check

Metrics

Logs

Tracing

Audit Logs

---

# 16. Coding Requirements

Every service must include:

README

Dockerfile

docker-compose support

OpenAPI Specification

Unit Tests

Integration Tests

Migration Scripts

Configuration

Logging

Monitoring

Security Policies

---

# 17. Design Rules

✅ One responsibility per service

✅ One database owner per domain

✅ Publish domain events

✅ Consume events safely

✅ Prefer asynchronous communication

✅ Fail gracefully

✅ Retry transient failures

✅ Idempotent event handlers

✅ Version APIs

✅ Version events

---

# 18. Anti-Patterns

Do NOT:

❌ Build a monolith

❌ Share databases

❌ Hardcode configuration

❌ Store secrets in code

❌ Skip audit logging

❌ Ignore security

❌ Couple services tightly

❌ Duplicate business logic

❌ Call AI directly from UI

❌ Bypass the API Gateway

---

# 19. Future Expansion

The architecture should support:

- Multi-hospital deployments
- Regional health networks
- National health systems
- Medical IoT devices
- Smart wards
- Robotics
- Wearables
- Population health analytics
- Federated AI learning
- Research data platforms

---

# 20. Architectural Principle

> **Every service should be independently deployable, independently testable, independently scalable, and independently replaceable without disrupting the rest of the platform.**