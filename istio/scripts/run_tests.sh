
[ "${DEBUG}" = 'true' ] && set -x

for from in "foo" "bar" "legacy"; do
    sleep_pod=$(kubectl get pod -l app=sleep -n ${from} -o jsonpath={.items..metadata.name})
    for to in "foo" "bar" "legacy"; do
        kubectl exec "${sleep_pod}" -c sleep -n ${from} -- curl http://httpbin.${to}:8000/ip -s -o /dev/null -w "sleep.${from} to httpbin.${to}: %{http_code}\n"
    done
done
