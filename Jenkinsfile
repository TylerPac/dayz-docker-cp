// CI for the DayZ server + control panel (homelab fork).
//
//   check -> build image -> push to Gitea registry -> bump tag in KubernetesLab
//
// This pipeline never deploys. Argo CD notices the new tag in KubernetesLab
// (apps/gameservers/dayz/values.yaml) and rolls it out. The GitHub Actions
// workflow is upstream's and does not run here.
pipeline {
  agent {
    kubernetes {
      yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: python
      image: python:3.13-slim-trixie
      command: [sleep]
      args: [infinity]
    - name: buildkit
      image: moby/buildkit:v0.33.0
      securityContext:
        privileged: true
      command: [sleep]
      args: [infinity]
      volumeMounts:
        - {name: registry-auth, mountPath: /root/.docker}
    - name: git
      image: alpine/git:v2.54.0
      command: [sleep]
      args: [infinity]
  volumes:
    - name: registry-auth
      secret:
        secretName: gitea-registry-push
        items: [{key: .dockerconfigjson, path: config.json}]
'''
    }
  }

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    timeout(time: 45, unit: 'MINUTES')
  }

  environment {
    REGISTRY    = 'gitea.sirpacsterlab.com/sirpacster'
    IMAGE       = 'dayz-docker-cp'
    GITOPS_REPO = 'http://gitea.default.svc.cluster.local:3000/sirpacster/KubernetesLab.git'
    VALUES_FILE = 'apps/gameservers/dayz/values.yaml'
  }

  stages {
    stage('Version') {
      steps {
        script {
          env.TAG = "${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(7)}"
          currentBuild.displayName = env.TAG
        }
      }
    }

    stage('Check') {
      steps {
        container('python') {
          // Upstream has no unit tests (its checks run against a live
          // container), so this catches what can be caught without one:
          // syntax errors and an app that does not import.
          sh '''
            python -m compileall -q panel
            for f in docker/*.sh; do bash -n "$f"; done
            pip install -q --no-cache-dir -r panel/requirements.txt
            cd panel && ADMIN_PASSWORD=ci DATA_DIR=/tmp/ci-data AUTO_INSTALL=false \
              python -c "from app import create_app; create_app()"
          '''
        }
      }
    }

    stage('Build & push image') {
      steps {
        container('buildkit') {
          sh '''
            buildctl-daemonless.sh build \
              --frontend dockerfile.v0 \
              --local context=. --local dockerfile=. \
              --output type=image,name=$REGISTRY/$IMAGE:$TAG,push=true
          '''
        }
      }
    }

    stage('Bump tag in KubernetesLab') {
      steps {
        container('git') {
          withCredentials([usernamePassword(credentialsId: 'gitea', usernameVariable: 'GIT_USER', passwordVariable: 'GIT_TOKEN')]) {
            sh '''
              # Credentials via askpass so the token never appears in a URL or .git/config.
              printf '#!/bin/sh\\ncase "$1" in Username*) echo "$GIT_USER";; *) echo "$GIT_TOKEN";; esac\\n' > /tmp/askpass
              chmod +x /tmp/askpass
              export GIT_ASKPASS=/tmp/askpass

              rm -rf gitops && git clone --depth 1 "$GITOPS_REPO" gitops && cd gitops
              sed -i -E "/repository: .*\\/$IMAGE\\$/{n;s/(tag: )[^ ]+/\\1$TAG/}" "$VALUES_FILE"
              git diff --stat
              git -c user.name=jenkins -c user.email=jenkins@sirpacsterlab.com \
                commit -am "deploy(dayz): $TAG" -m "Built by Jenkins from dayz-docker-cp@$GIT_COMMIT"
              git push origin HEAD:main
            '''
          }
        }
      }
    }
  }
}
