package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/FurqanSoftware/slinky"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: slinky-profile <https-profile-url>")
		os.Exit(2)
	}
	parsed, err := slinky.Parse(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if parsed.Type != "User" || parsed.ID == "" || parsed.URL == nil {
		fmt.Fprintln(os.Stderr, "URL is not a supported social user profile")
		os.Exit(2)
	}
	if parsed.URL.Scheme != "https" {
		fmt.Fprintln(os.Stderr, "only HTTPS profile URLs are accepted")
		os.Exit(2)
	}
	_ = json.NewEncoder(os.Stdout).Encode(map[string]string{
		"id":  parsed.ID,
		"url": parsed.URL.String(),
	})
}
