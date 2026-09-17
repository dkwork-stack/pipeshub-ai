import { defineRailway, github, group, image, mongo, mysql, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  // --- Data Layer ---
  const MySQL = mysql("MySQL", { region: "sfo" });
  MySQL.deploy = { startCommand: "docker-entrypoint.sh mysqld --innodb-use-native-aio=0 --disable-log-bin --performance_schema=0 --innodb-buffer-pool-size=1G" };
  MySQL.networking = { privateNetworkEndpoint: "mysql" };

  const Redis = redis("Redis", { region: "sfo" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  Redis.networking = { privateNetworkEndpoint: "redis" };

  const MongoDB = mongo("MongoDB", { region: "sfo" });
  MongoDB.deploy = { startCommand: "docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false" };
  MongoDB.networking = { privateNetworkEndpoint: "mongodb" };

  const redisVolume = volume("redis-volume", { allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const mysqlVolume = volume("mysql-volume", { allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const mongodbVolume = volume("mongodb-volume", { allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const neo4jVolume = volume("neo4j-volume", { allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const qdrantVolume = volume("qdrant-volume", { allowOnlineResize: true, region: "sfo", sizeMB: 5000 });

  // Neo4j graph store. PIPESHUB_NEO4J_PASSWORD is the single source of truth for the
  // password; NEO4J_AUTH and the app's NEO4J_PASSWORD both reference it so it only
  // ever needs to be set/rotated in one place (mirrors the official PipesHub template).
  const neo4j = service("neo4j", {
    source: image("neo4j:5.26.0"),
    replicas: { "sfo": 1 },
    volumeMounts: { "/data": neo4jVolume },
    env: {
      NEO4J_AUTH: "neo4j/${{neo4j.PIPESHUB_NEO4J_PASSWORD}}",
      NEO4J_server_memory_heap_initial__size: "256m",
      NEO4J_server_memory_heap_max__size: "512m",
      NEO4J_server_memory_pagecache_size: "256m",
      // Rotate this value if reusing this file to seed an unrelated deployment.
      PIPESHUB_NEO4J_PASSWORD: "34672010e93e2c118ae42bc9c6883a7f",
    },
  });

  // Qdrant vector store. QDRANT_API_KEY is the single source of truth; both the
  // server enforcement var (QDRANT__SERVICE__API_KEY) and the app's client var
  // reference it, so the key is generated/rotated in exactly one place.
  const qdrant = service("qdrant", {
    source: image("qdrant/qdrant:v1.15"),
    replicas: { "sfo": 1 },
    volumeMounts: { "/qdrant/storage": qdrantVolume },
    env: {
      // Rotate this value if reusing this file to seed an unrelated deployment.
      QDRANT_API_KEY: "CfVbaAGXXUbuaggjgTUVDTsvx8ScPs4e",
      QDRANT__SERVICE__API_KEY: "${{qdrant.QDRANT_API_KEY}}",
    },
  });

  // --- Application ---
  const app = service("app", {
    source: github("dkwork-stack/pipeshub-ai", { branch: "feature/test1", checkSuites: false }),
    replicas: { "sfo": 1 },
    env: {
      PORT: "3000",
      // Self-references to the app's own generated public domain, same pattern the
      // official PipesHub Railway template uses for these two variables.
      ALLOWED_ORIGINS: "https://${{app.RAILWAY_PUBLIC_DOMAIN}}",
      FRONTEND_PUBLIC_URL: "https://${{app.RAILWAY_PUBLIC_DOMAIN}}",

      // Internal all-in-one service endpoints (connector/query/indexing/docling all
      // run inside the same container).
      CONNECTOR_BACKEND: "http://127.0.0.1:8088",
      QUERY_BACKEND: "http://127.0.0.1:8000",
      INDEXING_BACKEND: "http://127.0.0.1:8091",
      INTELLIGENCE_BACKEND: "http://127.0.0.1:8094",
      DOCLING_BACKEND: "http://127.0.0.1:8081",
      USE_PARSING_SERVICE: "true",

      DATA_STORE: "neo4j",
      NEO4J_URI: "bolt://${{neo4j.RAILWAY_PRIVATE_DOMAIN}}:7687",
      NEO4J_USERNAME: "neo4j",
      NEO4J_PASSWORD: "${{neo4j.PIPESHUB_NEO4J_PASSWORD}}",
      NEO4J_DATABASE: "neo4j",

      KV_STORE_TYPE: "redis",
      MESSAGE_BROKER: "redis",
      REDIS_HOST: "${{Redis.RAILWAY_PRIVATE_DOMAIN}}",
      REDIS_PORT: "6379",
      REDIS_PASSWORD: "${{Redis.REDIS_PASSWORD}}",
      REDIS_URL: "${{Redis.REDIS_URL}}",

      MONGO_URI: "${{MongoDB.MONGO_URL}}/enterprise-search?authSource=admin",
      MONGO_DB_NAME: "enterprise-search",

      QDRANT_HOST: "${{qdrant.RAILWAY_PRIVATE_DOMAIN}}",
      QDRANT_PORT: "6333",
      QDRANT_GRPC_PORT: "6334",
      QDRANT_API_KEY: "${{qdrant.QDRANT_API_KEY}}",

      // Customer Feature Intelligence store (reuses the native MySQL plugin).
      INTELLIGENCE_STORE_TYPE: "mysql",
      INTELLIGENCE_MYSQL_HOST: "${{MySQL.RAILWAY_PRIVATE_DOMAIN}}",
      INTELLIGENCE_MYSQL_PORT: "3306",
      INTELLIGENCE_MYSQL_USER: "root",
      INTELLIGENCE_MYSQL_PASSWORD: "${{MySQL.MYSQL_ROOT_PASSWORD}}",
      INTELLIGENCE_MYSQL_DATABASE: "${{MySQL.MYSQLDATABASE}}",

      // Rotate this value if reusing this file to seed an unrelated deployment.
      SECRET_KEY: "9763c85c559bd8f283ddf2b3bb212ed0cca446b1ea9af770ff6ea9faf815a7e1",
    },
  });

  group("Data Layer", [MySQL, Redis, MongoDB, neo4j, qdrant, redisVolume, mysqlVolume, mongodbVolume, neo4jVolume, qdrantVolume]);
  group("Application", [app]);

  return project("pipeshub-ai", {
    resources: [MySQL, Redis, MongoDB, app, neo4j, qdrant, redisVolume, mysqlVolume, mongodbVolume, neo4jVolume, qdrantVolume],
  });
});
