package main

import (
	"fmt"
	"github.com/gicmo/PiCo/hue"
)

func main() {

	client, err := hue.ReadConfig("/etc/pico")
	if err != nil {
		panic(err)
	}

	bridge := client.Bridge
	fmt.Printf("Bridge: %s [user: %s]\n", bridge.Address, bridge.Username)

	grpstate, err := bridge.IsOn(1)
	if err != nil {
		panic(err)
	}

	fmt.Printf("Group 1 is %v\n", grpstate)

	client.Toggle()

}
