package main

import (
	"fmt"
	"io/ioutil"
	"net/http"
	"sync"
)

func callHello() {
	resp, err := http.Get("http://localhost:9090/api")
	if err != nil {
		print(err)
	}

	defer resp.Body.Close()
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		print(err)
	}

	fmt.Print(string(body))
}

func main() {
	for {
		var wg sync.WaitGroup
		for i := 0; i < 5; i++ {
			wg.Add(1)
			go func() {
				callHello()
				wg.Done()
			}()
		}
		wg.Wait()
	}
}
