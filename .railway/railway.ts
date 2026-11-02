import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "web";
export default defineRailway(() => {
  const web = service("web", {
    source: github("darwinjoelap/ordo-salud", { branch: "main", checkSuites: false }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/salud/",
    healthcheckTimeout: 60,
    preDeploy: "python manage.py migrate --noinput",
    replicas: { "us-west2": 1 },
    domains: ["*.salud.ordove.com"],
    networking: { privateNetworkEndpoint: "ordo-salud" },
  });

  return project("ordo-salud", {
    variables: { managed: false },
    resources: [web],
  });
});
