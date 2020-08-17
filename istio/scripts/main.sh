
Istio 

Entry layer
    - Gateway (Ingress/Egress) - Standalone Envoy

Routing layer (defined per service)
    - VirtualService (Routes based on rules) Subset based routing weighted/header based route
    - DestinationRule - Here u define Subset


Security
    - mTLS encryption
    - AAA (Authentication/Authorization/Audit)

kubectl create namespace foo
kubectl label namespace foo istio-injection=enabled --overwrite
kubectl create namespace bar
kubectl label namespace bar istio-injection=enabled --overwrite
kubectl create namespace legacy

kubectl get namespaces --show-labels

kubectl apply -f scripts/httpbin.yaml -n foo
kubectl apply -f scripts/sleep.yaml -n foo
kubectl apply -f scripts/httpbin.yaml -n bar
kubectl apply -f scripts/sleep.yaml -n bar
kubectl apply -f scripts/httpbin.yaml -n legacy
kubectl apply -f scripts/sleep.yaml -n legacy

./scripts/run_tests.sh


# Let's enable strict mTLS for foo and bar
kubectl apply -f - <<EOF
apiVersion: "security.istio.io/v1beta1"
kind: "PeerAuthentication"
metadata:
  name: "default"
  namespace: "foo"
spec:
  mtls:
    mode: STRICT
EOF
kubectl apply -f - <<EOF
apiVersion: "security.istio.io/v1beta1"
kind: "PeerAuthentication"
metadata:
  name: "default"
  namespace: "bar"
spec:
  mtls:
    mode: STRICT
EOF
./scripts/run_tests.sh


# Let deny all traffic to httpbin.foo from ouside of foo
cat <<EOF | kubectl apply -f -
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
 name: httpbin-deny
 namespace: foo
spec:
 selector:
   matchLabels:
     app: httpbin
     version: v1
 action: DENY
 rules:
 - from:
   - source:
       notNamespaces: ["foo"]
EOF
./scripts/run_tests.sh


# Let's deny all traffic to on foo namespace
cat <<EOF | kubectl apply -f -
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: foo
EOF
./scripts/run_tests.sh



# Allow httpbin.foo from sleep.foo alone
cat <<EOF | kubectl apply -f -
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
 name: httpbin-allow-sleep
 namespace: foo
spec:
 selector:
   matchLabels:
     app: httpbin
 action: ALLOW
 rules:
 - from:
   - source:
       principals: ["cluster.local/ns/foo/sa/sleep"]
   to:
   - operation:
       methods: ["GET"]
EOF
./scripts/run_tests.sh



kubectl delete AuthorizationPolicy httpbin-deny -n foo
kubectl delete AuthorizationPolicy httpbin-allow-sleep -n foo
kubectl delete AuthorizationPolicy deny-all -n foo
kubectl delete PeerAuthentication default -n foo
kubectl delete PeerAuthentication default -n bar
kubectl delete ns foo bar legacy
