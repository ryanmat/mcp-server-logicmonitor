{{/*
Description: Helper templates for LogicMonitor MCP server Helm chart.
Description: Provides common name and label generation functions.
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "lm-mcp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "lm-mcp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "lm-mcp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "lm-mcp.labels" -}}
helm.sh/chart: {{ include "lm-mcp.chart" . }}
{{ include "lm-mcp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "lm-mcp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lm-mcp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "lm-mcp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "lm-mcp.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the secret to use
*/}}
{{- define "lm-mcp.secretName" -}}
{{- if .Values.logicmonitor.existingSecret }}
{{- .Values.logicmonitor.existingSecret }}
{{- else }}
{{- include "lm-mcp.fullname" . }}
{{- end }}
{{- end }}
