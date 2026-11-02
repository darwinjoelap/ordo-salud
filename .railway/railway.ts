import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "web";
export default defineRailway(() => {
  const repo = github("darwinjoelap/ordo-salud", { branch: "main", checkSuites: false });
  const docker = { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" } as const;

  const web = service("web", {
    source: repo,
    build: docker,
    healthcheck: "/salud/",
    healthcheckTimeout: 60,
    preDeploy: "python manage.py migrate --noinput",
    replicas: { "us-west2": 1 },
    domains: ["*.salud.ordove.com"],
    networking: { privateNetworkEndpoint: "ordo-salud" },
  });

  // Tareas programadas (ADR-056): tasa BCV, cierre de consultas vencidas y limpiezas.
  // 11:00 y 22:00 UTC = 07:00 y 18:00 en Venezuela. Corre, termina y el contenedor se apaga (sin reinicios).
  // Variables: se cargan en el panel de Railway (este archivo no maneja variables).
  const tareas = service("tareas", {
    source: repo,
    build: docker,
    replicas: { "us-west2": 1 },
    deploy: {
      startCommand: "python manage.py tareas_programadas",
      cronSchedule: "0 11,22 * * *",
      restartPolicyType: "NEVER",
    },
  });

  return project("ordo-salud", {
    variables: { managed: false },
    resources: [web, tareas],
  });
});
