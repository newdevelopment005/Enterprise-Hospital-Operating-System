{{/*
EHOS common helpers.
*/}}
{{- define "ehos.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ehos.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ehos.image" -}}
{{- $reg := .Values.global.imageRegistry | default "ehos" -}}
{{- printf "%s/%s:%s" $reg .image .Values.global.imageTag -}}
{{- end }}

{{- define "ehos.labels" -}}
app.kubernetes.io/name: "{{ include "ehos.name" . }}"
app.kubernetes.io/instance: "{{ .Release.Name }}"
app.kubernetes.io/part-of: ehos
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}